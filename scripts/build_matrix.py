#!/usr/bin/env python3
"""Generate the package × OpenWrt × package-architecture build matrix."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "metadata/mainstream-support.json"
SOURCE_LOCK = ROOT / "metadata/source-lock.json"
SOURCE_IDENTITIES = {
    "luci-app-nginx-manager": ("https://github.com/hello-yunshu/luci-app-nginx-manager", "."),
    "luci-app-cloudflare-ip": ("https://github.com/hello-yunshu/luci-app-cloudflare-ip", "package/luci-app-cloudflare-ip"),
    "luci-app-upnp-nat-relay": ("https://github.com/hello-yunshu/luci-app-upnp-nat-relay", "package/luci-app-upnp-nat-relay"),
    "luci-app-openclash": ("https://github.com/vernesong/OpenClash", "luci-app-openclash"),
    "luci-app-performance-manager-all": ("https://github.com/hello-yunshu/luci-app-performance-manager", "package/luci-app-performance-manager-all"),
    "rill-runtime-manager": ("https://github.com/hello-yunshu/rill-openwrt-packages", "package/rill-runtime-manager"),
}


def load_matrix() -> dict:
    return json.loads(SUPPORT.read_text(encoding="utf-8"))


def pending_source_locks(data: dict | None = None) -> list[tuple[str, str]]:
    data = data or load_matrix()
    lock = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))
    if lock.get("schemaVersion") != 1:
        raise ValueError("unsupported source lock schema")
    package_locks = lock.get("packages", {})
    all_packages = set(data["packages"])
    pending = []
    for package_name in sorted(all_packages):
        if package_name == "rill-runtime":
            artifact_lock = lock.get("rillRuntime", {})
            values = (artifact_lock.get("releaseTag"), artifact_lock.get("releaseId"),
                     artifact_lock.get("qualificationSha256"), artifact_lock.get("sha256SumsSha256"),
                     artifact_lock.get("packageCommit"))
            valid_release_lock = (
                artifact_lock.get("state") == "locked"
                and isinstance(values[0], str) and re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+-r[0-9]+", values[0])
                and (isinstance(values[1], int) or (isinstance(values[1], str) and values[1].isdigit()))
                and isinstance(values[2], str) and re.fullmatch(r"[0-9a-f]{64}", values[2])
                and isinstance(values[3], str) and re.fullmatch(r"[0-9a-f]{64}", values[3])
                and isinstance(values[4], str) and re.fullmatch(r"[0-9a-f]{40}", values[4])
            )
            if not valid_release_lock:
                pending.append((package_name, artifact_lock.get("reason", "incomplete immutable Rill release lock")))
            continue
        package_lock = package_locks.get(package_name, {})
        ref = package_lock.get("ref")
        expected_repository, expected_path = SOURCE_IDENTITIES[package_name]
        package_version = package_lock.get("packageVersion")
        repository = str(package_lock.get("repository", "")).removesuffix(".git")
        source_path = package_lock.get("path")
        if (
            package_lock.get("state") != "locked"
            or not isinstance(ref, str)
            or not re.fullmatch(r"[0-9a-f]{40}", ref)
            or repository != expected_repository
            or not isinstance(source_path, str)
            or not source_path
            or source_path != expected_path
            or not isinstance(package_version, str)
            or not package_version
            or (isinstance(source_path, str) and source_path != "." and (source_path.startswith("/") or ".." in Path(source_path).parts))
        ):
            pending.append((package_name, package_lock.get("reason", "source ref is not a full immutable commit SHA")))
    rill_lock = lock.get("rillRuntime", {})
    manager_lock = package_locks.get("rill-runtime-manager", {})
    if (
        rill_lock.get("state") == "locked"
        and manager_lock.get("state") == "locked"
        and rill_lock.get("packageCommit") != manager_lock.get("ref")
    ):
        pending.append(("rill-runtime-manager", "manager package source must be the exact same Rill commit qualified by the Stable Runtime release"))
    rill_repository = str(rill_lock.get("repository", "")).removesuffix(".git")
    manager_repository = str(manager_lock.get("repository", "")).removesuffix(".git")
    if rill_lock.get("state") == "locked" and rill_repository != "https://github.com/hello-yunshu/rill-openwrt-packages":
        pending.append(("rill-runtime", "qualified Stable Runtime release must come from the Rill repository"))
    if manager_lock.get("state") == "locked" and (
        manager_repository != rill_repository
        or manager_lock.get("path") != "package/rill-runtime-manager"
    ):
        pending.append(("rill-runtime-manager", "manager source must come from the locked Rill repository package path"))
    return pending


def generate(scope: str = "all-required") -> list[dict]:
    data = load_matrix()
    lock = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))
    package_locks = lock.get("packages", {})
    pending = pending_source_locks(data)
    all_packages = set(data["packages"])
    if scope not in ("all-required", "available-only"):
        raise ValueError(f"unknown build scope: {scope}")
    if scope == "all-required" and pending:
        raise ValueError("required source locks are pending:\n" + "\n".join(f"- {name}: {reason}" for name, reason in pending))
    available = all_packages - {name for name, _ in pending}
    rows = []
    for package_name, package in data["packages"].items():
        if package_name not in available:
            continue
        allowed_arches = set(package["architectures"])
        for release in data["releases"]:
            for arch in data["architectures"]:
                package_arch = arch["packageArch"]
                if package_arch not in allowed_arches:
                    continue
                target = arch["targets"][0]
                source_lock = lock.get("rillRuntime", {}) if package_name == "rill-runtime" else package_locks[package_name]
                rows.append({
                    "package": package_name,
                    "buildMode": (
                        "qualified-release-artifact"
                        if package_name == "rill-runtime"
                        else "sdk-package-build"
                    ),
                    "repository": source_lock.get("repository", ""),
                    "sourcePath": source_lock.get("path", ""),
                    "sourceRef": source_lock.get("ref") or source_lock.get("releaseTag"),
                    "expectedPackageVersion": source_lock.get("packageVersion", ""),
                    "rillSourceCommit": (
                        package_locks["rill-runtime-manager"].get("ref", "")
                        if package_name in {"luci-app-cloudflare-ip", "luci-app-performance-manager-all"}
                        else ""
                    ),
                    "openwrtVersion": release["version"],
                    "packageFormat": release["packageFormat"],
                    "packageManager": release["packageManager"],
                    "packageArch": package_arch,
                    "rustTarget": arch.get("rustTarget"),
                    "target": target["target"],
                    "subtarget": target["subtarget"],
                    "sdkPrefix": target["sdkPrefix"],
                    "sdkTag": f"{target['sdkPrefix']}-v{release['version']}",
                })
    return rows


def index_matrix(scope: str = "all-required") -> list[dict]:
    rows = generate(scope)
    selected = sorted({row["packageArch"] for row in rows})
    data = load_matrix()
    result = []
    for release in data["releases"]:
        for arch in data["architectures"]:
            if arch["packageArch"] not in selected:
                continue
            result.append({
                "openwrtVersion": release["version"],
                "packageFormat": release["packageFormat"],
                "packageArch": arch["packageArch"],
                "sdkTag": f"x86_64-v{release['version']}",
            })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output", help="append a GitHub Actions matrix output to this file")
    parser.add_argument("--scope", choices=("all-required", "available-only"), default="all-required")
    parser.add_argument("--counts", action="store_true", help="print the matrix row count instead of JSON")
    parser.add_argument("--show-pending", action="store_true", help="report the complete proposed matrix and pending locks without building")
    args = parser.parse_args()
    if args.show_pending:
        data = load_matrix()
        all_rows = 0
        for package in data["packages"].values():
            all_rows += len(data["releases"]) * len(package["architectures"])
        locked_rows = len(generate("available-only"))
        print(json.dumps({
            "proposedBuildRows": all_rows,
            "lockedBuildRows": locked_rows,
            "pendingSourceLocks": [{"package": package, "reason": reason} for package, reason in pending_source_locks(data)],
        }, indent=2))
        return 0
    rows = generate(args.scope)
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as output:
            runtime_rows = [row for row in rows if row["package"] == "rill-runtime"]
            build_rows = [row for row in rows if row["buildMode"] == "sdk-package-build"]
            output.write("matrix=" + json.dumps({"include": build_rows}, separators=(",", ":")) + "\n")
            output.write("runtime_matrix=" + json.dumps({"include": runtime_rows}, separators=(",", ":")) + "\n")
            output.write("runtime_count=" + str(len(runtime_rows)) + "\n")
            output.write("index_matrix=" + json.dumps({"include": index_matrix(args.scope)}, separators=(",", ":")) + "\n")
            output.write("packages=" + ",".join(sorted({row["package"] for row in rows})) + "\n")
    if args.counts:
        print(len(rows))
    elif not args.github_output:
        json.dump({"include": rows}, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
