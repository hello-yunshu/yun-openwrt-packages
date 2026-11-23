from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/patch_mosdns_static.py"
SPEC = importlib.util.spec_from_file_location("patch_mosdns_static", SCRIPT)
assert SPEC and SPEC.loader
patcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patcher)

MAKEFILE = """\
include $(TOPDIR)/rules.mk
PKG_NAME:=mosdns

include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/golang/golang-package.mk

define Package/mosdns
  TITLE:=A plug-in DNS forwarder
endef

$(eval $(call GoBinPackage,mosdns))
$(eval $(call BuildPackage,mosdns))
"""


class StaticLinkPatchTests(unittest.TestCase):
    def _write(self, directory: str, text: str = MAKEFILE) -> Path:
        path = Path(directory) / "Makefile"
        path.write_text(text, encoding="utf-8")
        return path

    def test_override_lands_after_the_golang_include(self):
        with tempfile.TemporaryDirectory() as tmp:
            makefile = self._write(tmp)
            self.assertTrue(patcher.apply(makefile))
            lines = makefile.read_text(encoding="utf-8").splitlines()
        include_at = next(i for i, l in enumerate(lines) if l.startswith("include") and "golang-package.mk" in l)
        override_at = lines.index(patcher.OVERRIDE)
        eval_at = next(i for i, l in enumerate(lines) if "GoBinPackage" in l)
        self.assertEqual(override_at, include_at + 1)
        # 必须早于 eval：GoBinPackage 是立即展开的宏，读到的是展开时的变量值，
        # 追加到文件末尾就太晚了。
        self.assertLess(override_at, eval_at)

    def test_second_run_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            makefile = self._write(tmp)
            self.assertTrue(patcher.apply(makefile))
            before = makefile.read_text(encoding="utf-8")
            self.assertFalse(patcher.apply(makefile))
            self.assertEqual(makefile.read_text(encoding="utf-8"), before)

    def test_missing_anchor_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            makefile = self._write(tmp, "PKG_NAME:=mosdns\n")
            with self.assertRaises(SystemExit):
                patcher.apply(makefile)


if __name__ == "__main__":
    unittest.main()
