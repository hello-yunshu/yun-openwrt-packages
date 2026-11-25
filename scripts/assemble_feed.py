#!/usr/bin/env python3
"""Stage a complete candidate feed from already-qualified package artifacts.

Input layout:  <artifacts>/<openwrt-version>/<package-arch>/*.{ipk,apk}
Output layout: <output>/<openwrt-version>/<package-arch>/*.{ipk,apk}

This script does not build, sign, publish, or upgrade packages. It refuses an
incomplete package/architecture set so a partial candidate cannot be mistaken
for a complete release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "metadata/mainstream-support.json"
QUALIFICATION_LEVELS = {"build-verified", "build-install-qualified", "device-runtime-qualified"}
sys.path.insert(0, str(ROOT / "scripts"))
from validate_mainstream_support import covers_release, validate as validate_support_matrix


def expected_files(selected_packages: set[str] | None = None) -> dict[tuple[str, str], list[tuple[str, str]]]:
    data = json.loads(SUPPORT.read_text(encoding="utf-8"))
    validate_support_matrix(data)
    result: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for package_name, package in data["packages"].items():
        if selected_packages is not None and package_name not in selected_packages:
            continue
        for release in data["releases"]:
            if not covers_release(package, release["version"]):
                continue
            extension = ".ipk" if release["packageFormat"] == "ipk" else ".apk"
            for arch in package["architectures"]:
                result.setdefault((release["version"], arch), []).append((package_name, extension))
    return result


def qualification_summary(data: dict, selected: set[str],
                          verified_cells: set[tuple[str, str, str]] | None = None
                          ) -> tuple[list[dict], list[dict], dict[str, int]]:
    levels = []
    unqualified = []
    arch_names = {arch["packageArch"] for arch in data["architectures"]}
    release_names = {release["version"] for release in data["releases"]}
    expected_keys = {
        (package, release, arch)
        for package in selected
        for release in release_names
        for arch in arch_names
        if covers_release(data["packages"][package], release)
    }
    rows = [row for row in data.get("qualificationMatrix", []) if row.get("package") in selected]
    recorded = {
        (row.get("package"), row.get("openwrtVersion"), row.get("packageArch")): row
        for row in rows
    }
    if len(recorded) != len(rows):
        raise ValueError("qualification matrix is duplicated for selected feed packages")
    unexpected = set(recorded) - expected_keys
    if unexpected:
        raise ValueError(f"qualification matrix has cells outside the declared inventory: {sorted(unexpected)}")
    verified_cells = verified_cells or set()
    counts = {
        "build-verified": 0,
        "build-install-qualified": 0,
        "device-runtime-qualified": 0,
        "unsupported": 0,
        "pending": 0,
    }
    for package, release, arch in sorted(expected_keys):
        row = recorded.get((package, release, arch))
        if row is None:
            # A newly declared package has no qualification rows yet. Derive the
            # cell from the package's declared architectures instead of failing
            # the whole feed: excluded arches are unsupported and the rest stay
            # pending until this run or a later qualification record covers them.
            supported = arch in set(data["packages"][package]["architectures"])
            level = "pending" if supported else "unsupported"
            if supported and (package, release, arch) in verified_cells:
                level = "build-verified"
            item = {
                "package": package,
                "openwrtVersion": release,
                "packageArch": arch,
                "level": level,
                "runtimeCheck": "pending" if supported else "not-applicable",
            }
        else:
            status = row.get("status", "pending")
            level = status if status in QUALIFICATION_LEVELS or status == "unsupported" else "pending"
            # A cell becomes build-verified when this run produced and validated
            # its exact artifact. It never claims install, upgrade, or device runtime.
            if level == "pending" and (package, release, arch) in verified_cells:
                level = "build-verified"
            item = {
                "package": package,
                "openwrtVersion": release,
                "packageArch": arch,
                "level": level,
                "runtimeCheck": row.get("checks", {}).get("runtime", "pending"),
            }
        counts[level] += 1
        levels.append(item)
        if level == "pending":
            unqualified.append(item)
    return levels, unqualified, counts


def stage(artifacts: Path, output: Path, selected_packages: set[str] | None = None) -> int:
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory is not empty: {output}")
    data = json.loads(SUPPORT.read_text(encoding="utf-8"))
    validate_support_matrix(data)
    source_lock_data = json.loads((ROOT / "metadata/source-lock.json").read_text(encoding="utf-8"))
    all_packages = set(data["packages"])
    selected = all_packages if selected_packages is None else selected_packages
    unknown = selected - all_packages
    if unknown:
        raise ValueError(f"unknown package(s) requested: {sorted(unknown)}")
    expected = expected_files(selected)
    copy_plan: list[tuple[Path, Path]] = []
    errors: list[str] = []
    verified_cells: set[tuple[str, str, str]] = set()
    for (release, arch), packages in sorted(expected.items()):
        source_dir = artifacts / release / arch
        for package_name, extension in packages:
            if package_name == "rill-runtime":
                expected_name = f"rill-runtime-v{release}-{arch}{extension}"
                matches = [source_dir / expected_name] if (source_dir / expected_name).is_file() else []
            elif extension == ".ipk":
                # Package archs such as aarch64_cortex-a53 and
                # arm_cortex-a7_neon-vfpv4 contain hyphens, so the arch field
                # must allow them or those artifacts are never matched.
                pattern = re.compile(rf"^{re.escape(package_name)}_[0-9][A-Za-z0-9.+_~:-]*_(?:all|noarch|[A-Za-z0-9_-]+)\.ipk$")
                matches = sorted(p for p in source_dir.glob("*.ipk") if pattern.fullmatch(p.name))
            else:
                pattern = re.compile(rf"^{re.escape(package_name)}-[0-9][A-Za-z0-9.+_~:-]*\.apk$")
                matches = sorted(p for p in source_dir.glob("*.apk") if pattern.fullmatch(p.name))
            if len(matches) != 1:
                errors.append(f"{release}/{arch}: expected exactly one {package_name} *{extension}; found {len(matches)}")
                continue
            evidence_path = source_dir / f"{package_name}.build-evidence.json"
            if not evidence_path.is_file():
                errors.append(f"{release}/{arch}: missing build evidence for {package_name}")
                continue
            try:
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                errors.append(f"{release}/{arch}: invalid build evidence for {package_name}")
                continue
            if (
                evidence.get("package") != package_name
                or evidence.get("openwrtVersion") != release
                or evidence.get("packageArch") != arch
                or evidence.get("packageFormat") != ("ipk" if extension == ".ipk" else "apk")
                or evidence.get("packageSha256") != hashlib.sha256(matches[0].read_bytes()).hexdigest()
                or not evidence.get("sourceRef")
            ):
                errors.append(f"{release}/{arch}: build evidence identity or package digest mismatch for {package_name}")
                continue
            locked = (
                source_lock_data.get("rillRuntime", {})
                if package_name == "rill-runtime"
                else source_lock_data.get("packages", {}).get(package_name, {})
            )
            if locked.get("state") == "locked":
                expected_ref = locked.get("releaseTag") if package_name == "rill-runtime" else locked.get("ref")
                if evidence.get("sourceRef") != expected_ref:
                    errors.append(f"{release}/{arch}: build evidence sourceRef differs from immutable source lock for {package_name}")
                    continue
                expected_version = locked.get("packageVersion")
                if expected_version:
                    filename = matches[0].name
                    version_matches = (
                        filename.startswith(f"{package_name}_{expected_version}_")
                        or filename.startswith(f"{package_name}_{expected_version}-r")
                        if extension == ".ipk"
                        # APK filenames carry PKG_RELEASE only when it is
                        # non-zero, so a package at release 0 produces
                        # name-version.apk without the "-r" suffix.
                        else filename == f"{package_name}-{expected_version}{extension}"
                        or filename.startswith(f"{package_name}-{expected_version}-r")
                    )
                    if package_name == "rill-runtime":
                        version_matches = evidence.get("packageVersion") == expected_version
                    if not version_matches or evidence.get("packageVersion") != expected_version:
                        errors.append(f"{release}/{arch}: package version differs from immutable source lock for {package_name}")
                        continue
            destination = output / release / arch / matches[0].name
            if package_name == "rill-runtime" and extension == ".apk":
                # apk resolves downloads as <name>-<version>.apk and the v3
                # index does not carry filenames, so a published tree that
                # keeps the imported multi-arch asset name 404s on every
                # install. Stage it under the canonical name instead; the
                # imported name stays confined to the artifact directory.
                full_version = str(locked.get("releaseTag") or "").removeprefix("v")
                if full_version:
                    destination = output / release / arch / f"{package_name}-{full_version}{extension}"
            copy_plan.append((matches[0], destination))
            copy_plan.append((evidence_path, output / release / arch / evidence_path.name))
            for provenance in sorted(source_dir.glob("*.qualification.json")) + sorted(source_dir.glob("*.SHA256SUMS")):
                copy_plan.append((provenance, output / release / arch / provenance.name))
            verified_cells.add((package_name, release, arch))
    if errors:
        raise ValueError("incomplete package artifact matrix:\n" + "\n".join(errors))
    for source, destination in copy_plan:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    output.mkdir(parents=True, exist_ok=True)
    pending = sorted(all_packages - selected)
    qualification_levels, unqualified, qualification_counts = qualification_summary(data, selected, verified_cells)
    publishable = not pending and not unqualified
    candidate = {
        "schemaVersion": 1,
        "status": "publishable-candidate" if publishable else ("partial-candidate" if pending else "unqualified-candidate"),
        "publishable": publishable,
        "packages": sorted(selected),
        "omittedPackages": pending,
        "qualificationLevels": qualification_levels,
        "qualificationSummary": qualification_counts,
        "qualificationPolicy": "automatic-build-verified",
        "unqualifiedCells": unqualified,
        "sourceLockSha256": hashlib.sha256((ROOT / "metadata/source-lock.json").read_bytes()).hexdigest(),
        # Identifies the feed run that produced this candidate. YunWrt compares
        # it with the dispatch payload so a stale Pages copy is not mistaken for
        # the freshly deployed index.
        "buildId": os.environ.get("FEED_BUILD_ID", ""),
    }
    (output / "candidate.json").write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    return sum(len(packages) for packages in expected.values())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--packages", help="comma-separated package names for an explicitly partial candidate")
    args = parser.parse_args()
    selected = set(args.packages.split(",")) if args.packages else None
    count = stage(args.artifacts, args.output, selected)
    print(f"staged {count} package artifacts under {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
