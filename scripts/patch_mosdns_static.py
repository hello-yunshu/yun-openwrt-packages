#!/usr/bin/env python3
"""Force static linking for the mosdns Go binary.

OpenWrt's golang helpers default to ``-linkmode external`` without ``-static``,
so the produced binary links against musl dynamically. Two consequences:

* it cannot run outside the target rootfs — including on the CI runner, where
  the release gate needs to execute it. execve fails with ENOENT because the
  musl loader is absent, which looks like a broken gate rather than a binary
  that simply cannot run there;
* it comes out larger than the upstream release, which is built with
  ``GO_PKG_DEFAULT_LDFLAGS:=-w -s -extldflags "-static"``.

Upstream's own workflow applies exactly this override. Idempotent: running it
twice leaves the Makefile unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

OVERRIDE = 'GO_PKG_DEFAULT_LDFLAGS:=-w -s -extldflags "-static"'
ANCHOR = "golang-package.mk"


def apply(makefile: Path) -> bool:
    """Insert the override after the golang-package.mk include.

    It must land *before* the ``$(eval $(call GoBinPackage,...))`` lines, since
    that macro expands immediately and reads the variable at expansion time —
    appending to the end of the file would be too late.
    """
    text = makefile.read_text(encoding="utf-8")
    if OVERRIDE in text:
        return False
    lines = text.splitlines()
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and ANCHOR in line and line.lstrip().startswith("include"):
            out.append(OVERRIDE)
            inserted = True
    if not inserted:
        raise SystemExit(f"在 {makefile} 里找不到 include ...{ANCHOR}，无法插入静态链接覆盖")
    makefile.write_text("\n".join(out) + "\n", encoding="utf-8")
    return True


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("用法: patch_mosdns_static.py <mosdns/Makefile>")
    makefile = Path(sys.argv[1])
    if not makefile.is_file():
        raise SystemExit(f"找不到 {makefile}")
    changed = apply(makefile)
    print(("已插入" if changed else "已存在，跳过") + f"：{OVERRIDE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
