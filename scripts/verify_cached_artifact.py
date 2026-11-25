#!/usr/bin/env python3
"""Verify a restored package artifact cell before it is reused.

An ``actions/cache`` restore is trusted only after its identity has been
re-checked against the immutable matrix row. ``assemble_feed.py`` remains the
authoritative whole-feed gate; this script is a fail-fast guard so a stale,
incomplete, or tampered cached cell cannot even reach the upload step.

The exact package-file naming rules mirror ``assemble_feed.py`` so a cached
cell and a freshly built cell are held to the same identity contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# Same naming rules as assemble_feed.stage(): the architecture field may carry
# hyphens, and APK releases are omitted when PKG_RELEASE is zero.
IPK_NAME = re.compile(
    r"^(?P<package>[A-Za-z0-9_.+-]+)_[0-9][A-Za-z0-9.+_~:-]*_(?:all|noarch|[A-Za-z0-9_-]+)\.ipk$"
)
APK_NAME = re.compile(r"^(?P<package>[A-Za-z0-9_.+-]+)-[0-9][A-Za-z0-9.+_~:-]*\.apk$")


def locate_artifact(source_dir: Path, package: str, package_format: str) -> Path:
    """Return the single package file that matches ``package`` in ``source_dir``."""
    if package_format == "ipk":
        pattern, suffix = IPK_NAME, ".ipk"
    elif package_format == "apk":
        pattern, suffix = APK_NAME, ".apk"
    else:
        raise ValueError(f"unsupported package format: {package_format}")
    candidates = [
        path for path in sorted(source_dir.iterdir())
        if path.is_file()
        and (match := pattern.fullmatch(path.name))
        and match.group("package") == package
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"{source_dir}: expected exactly one {package} *{suffix}; found {len(candidates)}"
        )
    return candidates[0]


def verify(
    source_dir: Path,
    *,
    package: str,
    openwrt_version: str,
    package_arch: str,
    package_format: str,
    sdk_tag: str,
    source_ref: str,
    expected_version: str,
) -> Path:
    """Validate that the restored cell belongs to this exact matrix row."""
    if not source_dir.is_dir():
        raise ValueError(f"{source_dir}: cached cell directory is missing")
    artifact = locate_artifact(source_dir, package, package_format)
    evidence_path = source_dir / f"{package}.build-evidence.json"
    if not evidence_path.is_file():
        raise ValueError(f"{source_dir}: missing build evidence for {package}")
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{source_dir}: invalid build evidence for {package}: {exc}") from exc

    expected = {
        "package": package,
        "openwrtVersion": openwrt_version,
        "packageArch": package_arch,
        "packageFormat": package_format,
        "sdkTag": sdk_tag,
        "sourceRef": source_ref,
        "packageVersion": expected_version,
        "packageSha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    }
    for key, want in expected.items():
        if evidence.get(key) != want:
            raise ValueError(
                f"{source_dir}: cached evidence {key} mismatch for {package}: "
                f"{evidence.get(key)!r} != {want!r}"
            )
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=Path, help="runner.temp/out root")
    parser.add_argument("--package", required=True)
    parser.add_argument("--openwrt-version", required=True)
    parser.add_argument("--package-arch", required=True)
    parser.add_argument("--package-format", choices=("ipk", "apk"), required=True)
    parser.add_argument("--sdk-tag", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args(argv)

    cell = args.artifacts / args.openwrt_version / args.package_arch
    try:
        artifact = verify(
            cell,
            package=args.package,
            openwrt_version=args.openwrt_version,
            package_arch=args.package_arch,
            package_format=args.package_format,
            sdk_tag=args.sdk_tag,
            source_ref=args.source_ref,
            expected_version=args.expected_version,
        )
    except ValueError as exc:
        print(f"cached artifact verification failed: {exc}", file=sys.stderr)
        return 1
    print(f"cached artifact verified: {artifact.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
