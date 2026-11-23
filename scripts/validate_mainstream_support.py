#!/usr/bin/env python3
"""Validate the user-facing OpenWrt release/architecture support inventory."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "metadata/mainstream-support.json"
GITHUB_REPOSITORY = re.compile(r"^https://github\.com/[^/]+/[^/]+?(?:\.git)?$")
QUALIFICATION_LEVELS = {"build-install-qualified", "device-runtime-qualified"}
BASE_EVIDENCE = (
    "sourceCommit", "buildRun", "buildEvidence", "signatureEvidence",
    "dependencyEvidence", "installEvidence", "upgradeEvidence",
)


def validate_qualified_evidence(row: dict, level: str, label: str) -> None:
    evidence = row.get("evidence")
    required = BASE_EVIDENCE + (("runtimeEvidence",) if level == "device-runtime-qualified" else ())
    if not isinstance(evidence, dict) or not all(evidence.get(key) for key in required):
        raise ValueError(f"{label} claims {level} without required evidence")
    if level == "build-install-qualified" and evidence.get("runtimeEvidence"):
        raise ValueError(f"{label} has device Runtime evidence but is labeled only build-install-qualified")


def release_series(version: str) -> str:
    return ".".join(str(version).split(".")[:2])


def covers_release(package: dict, release_version: str) -> bool:
    """Whether a package is published for an OpenWrt release.

    A package may restrict itself to some release series: nginx-quic pins both
    its nginx version and its cross-compile patch set to the feed branch of one
    release line, so it is not built (and not qualified) for the others.
    """
    declared = package.get("releaseSeries")
    return not declared or release_series(release_version) in declared


def validate(data: dict | None = None) -> dict:
    if data is None:
        data = json.loads(MATRIX.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1:
        raise ValueError("unsupported mainstream support schema")
    releases = {item["version"]: item["packageFormat"] for item in data["releases"]}
    expected_releases = {"24.10.8": "ipk", "25.12.6": "apk"}
    if releases != expected_releases:
        raise ValueError(f"release/package-format mismatch: {releases!r}")

    architectures = data.get("architectures", [])
    arch_names = [item.get("packageArch") for item in architectures]
    if len(arch_names) != len(set(arch_names)):
        raise ValueError("duplicate package architecture")
    if set(arch_names) != {
        "x86_64",
        "aarch64_generic",
        "aarch64_cortex-a53",
        "aarch64_cortex-a72",
        "aarch64_cortex-a76",
        "arm_cortex-a7_neon-vfpv4",
        "mipsel_24kc",
    }:
        raise ValueError("mainstream architecture inventory changed without review")
    if any(not item.get("targets") for item in architectures):
        raise ValueError("architecture lacks official target/subtarget mapping")

    packages = data.get("packages", {})
    runtime_arches = set(packages["rill-runtime"]["architectures"])
    pm_arches = set(packages["luci-app-performance-manager-all"]["architectures"])
    manager_arches = set(packages["rill-runtime-manager"]["architectures"])
    cfi_arches = set(packages["luci-app-cloudflare-ip"]["architectures"])
    if runtime_arches != pm_arches:
        raise ValueError("PM and Rill Runtime architecture sets must match")
    if runtime_arches != {name for name, entry in zip(arch_names, architectures) if entry["rillRuntimeCandidate"]}:
        raise ValueError("Runtime candidate flags disagree with package architecture sets")
    if manager_arches != set(arch_names) or cfi_arches != set(arch_names):
        raise ValueError("CFI and Runtime Manager should include every selected feed architecture")
    for name, item in packages.items():
        if name != "rill-runtime":
            repository = item.get("repository")
            path = item.get("path")
            if not isinstance(repository, str) or not GITHUB_REPOSITORY.fullmatch(repository):
                raise ValueError(f"{name} must declare its source GitHub repository")
            if (
                not isinstance(path, str)
                or not path
                or path.startswith("/")
                or ".." in Path(path).parts
            ):
                raise ValueError(f"{name} must declare a relative source path")
        local_release = item.get("localRelease")
        if local_release is not None:
            # The value is spliced into PKG_RELEASE at build time as
            # upstream*100 + local, so it must be a bare 1-99 integer: anything
            # wider would collide with the next upstream release, and anything
            # non-numeric would break the sed or produce an invalid apk version.
            if not isinstance(local_release, str) or not re.fullmatch(r"[1-9][0-9]?", local_release):
                raise ValueError(f"{name} localRelease must be an integer string from 1 to 99")
        package_level = item.get("qualificationState", "pending")
        if package_level == "qualified":
            raise ValueError(f"{name} uses ambiguous qualificationState='qualified'; use an explicit qualification level")
        if package_level in QUALIFICATION_LEVELS:
            adapter = {"evidence": item.get("qualificationEvidence")}
            validate_qualified_evidence(adapter, package_level, name)

    # The package/release/architecture Cartesian matrix is the qualification
    # record, not a claim inferred from merely having an index directory.
    matrix = data.get("qualificationMatrix", [])
    expected_keys = {
        (package_name, release["version"], arch_name)
        for package_name, package in packages.items()
        for release in data["releases"]
        for arch_name in arch_names
    }
    actual_keys = [
        (row.get("package"), row.get("openwrtVersion"), row.get("packageArch"))
        for row in matrix
    ]
    if len(actual_keys) != len(set(actual_keys)):
        raise ValueError("duplicate package/release/architecture qualification row")
    extra = sorted(set(actual_keys) - expected_keys)
    if extra:
        raise ValueError(f"qualification matrix rows are outside the declared inventory: {extra}")
    arch_by_name = {item["packageArch"]: item for item in architectures}
    release_by_name = {item["version"]: item for item in data["releases"]}
    checks_required = ("build", "dependencyResolution", "signature", "cleanInstall", "upgrade", "runtime")
    for row in matrix:
        package = packages[row["package"]]
        release = release_by_name[row["openwrtVersion"]]
        arch = arch_by_name[row["packageArch"]]
        target = arch["targets"][0]
        if row.get("packageFormat") != release["packageFormat"]:
            raise ValueError(f"wrong package format in matrix row: {row}")
        if row.get("target") != target["target"] or row.get("subtarget") != target["subtarget"]:
            raise ValueError(f"wrong target identity in matrix row: {row}")
        supports_arch = row["packageArch"] in package["architectures"]
        status = row.get("status")
        allowed_statuses = {"pending", "unsupported", *QUALIFICATION_LEVELS}
        if status not in allowed_statuses:
            raise ValueError(f"matrix status disagrees with package capability: {row}")
        checks = row.get("checks", {})
        if not all(check in checks for check in checks_required):
            raise ValueError(f"matrix row omits a required qualification check: {row}")
        if not supports_arch and (status != "unsupported" or not row.get("reason") or any(checks[k] != "not-applicable" for k in checks_required)):
            raise ValueError(f"unsupported matrix row needs an exclusion reason: {row}")
        if supports_arch and status == "unsupported":
            raise ValueError(f"supported package architecture cannot be marked unsupported: {row}")
        if status == "pending" and not supports_arch:
            raise ValueError(f"unsupported package architecture must carry an exclusion: {row}")
        if status == "build-install-qualified":
            expected_checks = {key: "passed" for key in checks_required}
            expected_checks["runtime"] = "not-evaluated-device"
            if checks != expected_checks:
                raise ValueError(f"build/install-qualified row must leave device Runtime unevaluated: {row}")
            validate_qualified_evidence(row, status, str(row))
        if status == "device-runtime-qualified":
            if any(checks[key] != "passed" for key in checks_required):
                raise ValueError(f"device-runtime-qualified row has incomplete checks: {row}")
            validate_qualified_evidence(row, status, str(row))
    return data


if __name__ == "__main__":
    matrix = validate()
    print(f"validated {len(matrix['releases'])} releases, {len(matrix['architectures'])} mainstream architectures")
