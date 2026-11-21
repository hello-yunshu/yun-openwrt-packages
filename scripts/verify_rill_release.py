#!/usr/bin/env python3
"""Fail-closed verification of the exact immutable Rill release inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "metadata/mainstream-support.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(directory: Path, tag: str, release_id: str, qualification_sha256: str,
           sums_sha256: str, source_commit: str) -> dict:
    for name, value, pattern in (
        ("qualification SHA256", qualification_sha256, SHA256),
        ("SHA256SUMS SHA256", sums_sha256, SHA256),
        ("Rill source commit", source_commit, SHA1),
    ):
        if not pattern.fullmatch(value):
            raise ValueError(f"invalid locked {name}")
    if not str(release_id).isdigit() or int(release_id) <= 0:
        raise ValueError("invalid locked GitHub release ID")
    evidence_file = directory / "qualification.json"
    sums_file = directory / "SHA256SUMS"
    if not evidence_file.is_file() or digest(evidence_file) != qualification_sha256:
        raise ValueError("qualification.json is missing or its digest differs from the lock")
    if not sums_file.is_file() or digest(sums_file) != sums_sha256:
        raise ValueError("SHA256SUMS is missing or its digest differs from the lock")
    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    if evidence.get("schemaVersion") != 4 or evidence.get("qualificationState") != "automated-qualification" or evidence.get("releaseEligible") is not True:
        raise ValueError("Rill release is not backed by an eligible schema-4 Stable qualification")
    if evidence.get("packageCommit") != source_commit:
        raise ValueError("qualification packageCommit differs from the locked Rill source commit")
    package = evidence.get("package", {})
    if package.get("name") != "rill-runtime":
        raise ValueError("Rill release package identity is not the canonical Stable package")
    expected_tag = f"v{package.get('version')}-r{package.get('release')}"
    if expected_tag != tag:
        raise ValueError("release tag does not match qualified Stable package identity")

    support = json.loads(SUPPORT.read_text(encoding="utf-8"))
    expected = set()
    release_formats = {item["version"]: item["packageFormat"] for item in support["releases"]}
    for arch in support["architectures"]:
        if not arch.get("rillRuntimeCandidate"):
            continue
        for release in support["releases"]:
            target = arch["targets"][0]
            expected.add((release["version"], target["target"], target["subtarget"], arch["packageArch"], release_formats[release["version"]]))
    rows = evidence.get("targets", [])
    actual = set()
    runtime_files = set()
    for row in rows:
        identity = tuple(str(row.get(k, "")) for k in ("openwrtVersion", "target", "subtarget", "packageArch", "pkgtype"))
        if identity in actual:
            raise ValueError(f"duplicate Stable qualification row: {identity}")
        actual.add(identity)
        artifact = row.get("artifact", "")
        if not artifact or Path(artifact).name != artifact or artifact in runtime_files:
            raise ValueError("invalid or duplicate Stable asset name in qualification")
        runtime_files.add(artifact)
        asset = directory / artifact
        if not asset.is_file() or digest(asset) != row.get("sha256"):
            raise ValueError(f"Stable package asset is missing or differs from qualification: {artifact}")
        if row.get("qualificationState") != "PASS" or row.get("binary") != "/usr/bin/rill-runtime":
            raise ValueError(f"Stable target is not qualified: {identity}")
    if actual != expected:
        raise ValueError(f"Stable qualification targets differ from selected matrix: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")

    sums = {}
    for line in sums_file.read_text(encoding="utf-8").splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) != 2 or not SHA256.fullmatch(fields[0]):
            raise ValueError("malformed SHA256SUMS line")
        filename = fields[1].lstrip("* ")
        if Path(filename).name != filename or filename in sums:
            raise ValueError("unsafe or duplicate asset name in SHA256SUMS")
        sums[filename] = fields[0]
    downloaded = {p.name for p in directory.iterdir() if p.is_file() and p.suffix in (".ipk", ".apk")}
    if not downloaded or downloaded != set(sums):
        raise ValueError(f"downloaded Runtime assets differ from SHA256SUMS: unlisted={sorted(downloaded-set(sums))}, missing={sorted(set(sums)-downloaded)}")
    for filename, sha256 in sums.items():
        if digest(directory / filename) != sha256:
            raise ValueError(f"Rill release asset SHA256 mismatch: {filename}")
    if not runtime_files <= set(sums):
        raise ValueError("qualified Stable package is not included in locked release assets")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--qualification-sha256", required=True)
    parser.add_argument("--sha256-sums-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    evidence = verify(args.directory, args.tag, args.release_id, args.qualification_sha256,
                      args.sha256_sums_sha256, args.source_commit)
    print(json.dumps({"ok": True, "packageCommit": evidence["packageCommit"], "stableVersion": evidence["package"]["version"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
