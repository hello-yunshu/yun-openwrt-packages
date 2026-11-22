#!/usr/bin/env python3
"""Refresh metadata/source-lock.json from the newest stable upstream releases.

The feed build consumes immutable commit SHAs and release identities from
metadata/source-lock.json.  The authoritative package set comes from
metadata/mainstream-support.json; each support package must already have a lock
entry (repository, path, and optionally track) or the refresh fails closed.  The
script resolves each "release"-tracked package to its newest non-draft,
non-prerelease GitHub Release, pins the tag to its commit, and reads PKG_VERSION
from the package Makefile at that commit.  "rill-release" packages follow the
qualified Rill Runtime commit, "pinned" packages are left untouched, and Rill
Runtime itself is validated from the immutable qualification manifest published
with its release.  Nothing is written unless --write is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "metadata/source-lock.json"

RILL_REPOSITORY = "https://github.com/hello-yunshu/rill-openwrt-packages"
RILL_SLUG = "hello-yunshu/rill-openwrt-packages"
RILL_TAG = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+-r[0-9]+$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PKG_VERSION = re.compile(r"^PKG_VERSION:=\s*(\S.*?)\s*$")

DEFAULT_SUPPORT = ROOT / "metadata/mainstream-support.json"

RILL_RUNTIME = "rill-runtime"
TRACKS = ("release", "rill-release", "pinned")


def run_command(args: list[str], cwd: Path | None = None) -> str:
    """Run a non-interactive command and return stdout."""
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def slug_from_repository(repository: str) -> str:
    """Return the owner/repo slug for a GitHub HTTPS repository URL."""
    prefix = "https://github.com/"
    if not repository.startswith(prefix):
        raise ValueError(f"unsupported GitHub repository URL: {repository}")
    return repository[len(prefix):].removesuffix(".git").strip("/")


def load_support_packages(path: Path = DEFAULT_SUPPORT) -> dict[str, dict]:
    """Return the authoritative support-matrix package map, preserving order."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    packages = data.get("packages")
    if not isinstance(packages, dict) or not packages:
        raise ValueError("mainstream support matrix does not declare any packages")
    return packages


def _default_track(metadata: dict, repository) -> str:
    """Infer the default tracking mode from support metadata and source repo."""
    if metadata.get("rillRuntime") == "manager-only":
        return "rill-release"
    # Any package sourced from the Rill repository follows the qualified
    # Runtime commit unless it explicitly opts into its own release stream.
    if isinstance(repository, str) and repository.removesuffix(".git") == RILL_REPOSITORY:
        return "rill-release"
    return "release"


def fetch_releases(slug: str, runner=run_command) -> list[dict]:
    """Return the newest GitHub Releases for a repository slug."""
    output = runner(["gh", "api", f"repos/{slug}/releases?per_page=30"])
    releases = json.loads(output)
    if not isinstance(releases, list):
        raise ValueError(f"unexpected GitHub releases response for {slug}")
    return releases


def select_latest_stable(releases: list[dict], tag_pattern: re.Pattern | None = None) -> dict:
    """Return the newest release that is neither a draft nor a prerelease."""
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not tag:
            continue
        if tag_pattern is not None and not tag_pattern.fullmatch(tag):
            continue
        return release
    raise ValueError("no stable GitHub Release is available")


def resolve_tag_commit(repository: str, tag: str, runner=run_command) -> str:
    """Resolve an upstream tag to the commit it peels to."""
    output = runner([
        "git", "ls-remote", "--tags", repository,
        f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}",
    ])
    direct = None
    peeled = None
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        sha, ref = fields
        if ref == f"refs/tags/{tag}^{{}}":
            peeled = sha
        elif ref == f"refs/tags/{tag}":
            direct = sha
    commit = peeled or direct
    if not commit or not SHA1.fullmatch(commit):
        raise ValueError(f"cannot resolve a 40-character commit for {repository} tag {tag}")
    return commit


def parse_pkg_version(makefile: str) -> str:
    """Extract the single non-empty PKG_VERSION assignment from a Makefile."""
    values = []
    for line in makefile.splitlines():
        match = PKG_VERSION.fullmatch(line)
        if match:
            values.append(match.group(1).strip())
    if len(values) != 1 or not values[0]:
        raise ValueError("package Makefile must define exactly one non-empty PKG_VERSION")
    return values[0]


def read_makefile_version(repository: str, commit: str, path: str, runner=run_command) -> str:
    """Read PKG_VERSION from path/Makefile at an exact upstream commit."""
    if not SHA1.fullmatch(commit):
        raise ValueError(f"invalid immutable commit for {repository}: {commit}")
    makefile = "Makefile" if path in ("", ".") else f"{path.rstrip('/')}/Makefile"
    with tempfile.TemporaryDirectory() as directory:
        repository_dir = Path(directory)
        runner(["git", "init", "-q"], cwd=repository_dir)
        runner(["git", "remote", "add", "origin", repository], cwd=repository_dir)
        runner(["git", "fetch", "-q", "--depth", "1", "origin", commit], cwd=repository_dir)
        source = runner(["git", "show", f"{commit}:{makefile}"], cwd=repository_dir)
    return parse_pkg_version(source)


def download_rill_evidence(repository_url: str, tag: str, directory: Path, runner=run_command) -> dict:
    """Download and fingerprint the immutable qualification evidence for a tag."""
    directory = Path(directory)
    runner([
        "gh", "release", "download", tag,
        "--repo", slug_from_repository(repository_url),
        "--pattern", "qualification.json",
        "--pattern", "SHA256SUMS",
        "--dir", str(directory),
    ])
    qualification_file = directory / "qualification.json"
    sums_file = directory / "SHA256SUMS"
    if not qualification_file.is_file() or not sums_file.is_file():
        raise ValueError("Rill release is missing qualification.json or SHA256SUMS")
    return {
        "qualificationSha256": hashlib.sha256(qualification_file.read_bytes()).hexdigest(),
        "sha256SumsSha256": hashlib.sha256(sums_file.read_bytes()).hexdigest(),
        "qualification": json.loads(qualification_file.read_text(encoding="utf-8")),
    }


def validate_rill_qualification(qualification: dict, tag: str) -> tuple[str, str]:
    """Validate a Rill qualification manifest and return (packageCommit, version)."""
    if not isinstance(qualification, dict):
        raise ValueError("Rill qualification manifest is not a JSON object")
    if qualification.get("schemaVersion") != 4:
        raise ValueError("Rill qualification manifest schemaVersion is not 4")
    if qualification.get("qualificationState") != "automated-qualification":
        raise ValueError("Rill qualification manifest is not an automated qualification")
    if qualification.get("releaseEligible") is not True:
        raise ValueError("Rill qualification manifest is not release eligible")
    package = qualification.get("package")
    if not isinstance(package, dict) or package.get("name") != "rill-runtime":
        raise ValueError("Rill qualification manifest is not for rill-runtime")
    commit = qualification.get("packageCommit")
    if not isinstance(commit, str) or not SHA1.fullmatch(commit):
        raise ValueError("Rill qualification manifest has no immutable packageCommit")
    version = package.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("Rill qualification manifest has no package version")
    expected_tag = f"v{version}-r{package.get('release')}"
    if expected_tag != tag:
        raise ValueError(f"release tag does not match qualified Rill package identity: {tag} != {expected_tag}")
    return commit, version


def _declared_source(metadata: dict, entry: dict | None) -> tuple[str | None, str | None]:
    """Return the source identity declared by the support matrix or the lock.

    The support matrix is the authoritative package inventory, so a new package
    only needs ``repository`` and ``path`` there; the lock entry is optional and
    is created automatically.  If both places declare the same field they must
    agree, otherwise the refresh fails closed instead of silently repointing a
    package at another repository.
    """
    stored = entry if isinstance(entry, dict) else {}
    for field in ("repository", "path"):
        declared = metadata.get(field)
        locked = stored.get(field)
        if declared and locked and declared != locked:
            raise ValueError(
                f"package source {field} disagrees between the support matrix and "
                f"the source lock: {declared!r} != {locked!r}"
            )
    return metadata.get("repository") or stored.get("repository"), metadata.get("path") or stored.get("path")


def _package_identity(entry: dict) -> dict:
    return {key: entry.get(key) for key in ("repository", "path", "ref", "packageVersion", "state")}


def _apply_package(packages: dict, name: str, repository: str, path: str, ref: str,
                   version: str, changes: list[str]) -> None:
    desired = {
        "repository": repository,
        "path": path,
        "ref": ref,
        "packageVersion": version,
        "state": "locked",
    }
    existing = packages.get(name)
    if existing is None:
        packages[name] = desired
        changes.append(f"{name}: unset -> {ref}")
        return
    if _package_identity(existing) == desired:
        return
    old_ref = existing.get("ref")
    old_version = existing.get("packageVersion")
    existing.update(desired)
    if old_ref != ref:
        changes.append(f"{name}: {old_ref or 'unset'} -> {ref}")
    elif old_version != version:
        changes.append(f"{name}: {old_version or 'unset'} -> {version}")
    else:
        changes.append(f"{name}: source metadata updated")


def _rill_identity(entry: dict) -> dict:
    keys = (
        "repository", "packageCommit", "releaseTag", "releaseId",
        "qualificationSha256", "sha256SumsSha256", "state",
        "packageVersion", "channel",
        "qualificationRunId", "qualificationRunAttempt",
    )
    return {key: entry.get(key) for key in keys}


def update(lock: dict, release_api=None, tag_resolver=None, version_reader=None,
           rill_downloader=None, support_packages=None,
           support_path: Path = DEFAULT_SUPPORT) -> list[str]:
    """Resolve the newest upstream state and update lock in place.

    The feed package set comes from metadata/mainstream-support.json; the lock
    only supplies each package's repository, path, and optional ``track`` mode.
    A support-matrix package without a lock entry fails closed.  All upstream
    operations are injectable so tests never touch the network or a real
    git/gh checkout.
    """
    release_api = release_api or fetch_releases
    tag_resolver = tag_resolver or resolve_tag_commit
    version_reader = version_reader or read_makefile_version
    rill_downloader = rill_downloader or download_rill_evidence

    if support_packages is None:
        support = load_support_packages(support_path)
    elif isinstance(support_packages, dict):
        support = support_packages
    else:
        support = {name: {} for name in support_packages}

    packages = lock.setdefault("packages", {})
    previous_rill = lock.get("rillRuntime") or {}

    for name, metadata in support.items():
        if name == RILL_RUNTIME:
            if not isinstance(lock.get("rillRuntime"), dict):
                raise ValueError(
                    "support matrix package rill-runtime is missing from "
                    "metadata/source-lock.json (rillRuntime)"
                )
            continue
        entry = packages.get(name)
        if not isinstance(entry, dict):
            # A new package needs no lock template: the support matrix alone
            # declares where it comes from and the entry is created below.
            repository, path = _declared_source(metadata, None)
            if not repository or not path:
                raise ValueError(
                    f"support matrix package {name} is missing from metadata/source-lock.json "
                    "and declares no repository/path in the support matrix"
                )

    package_commit = None
    desired_rill = None
    if RILL_RUNTIME in support:
        # Resolve the immutable Runtime release first: packages tracked as
        # "rill-release" are pinned to exactly the commit it qualified.
        rill_release = select_latest_stable(release_api(RILL_SLUG), RILL_TAG)
        rill_tag = rill_release["tag_name"]
        release_id = rill_release.get("id")
        if isinstance(release_id, bool) or not isinstance(release_id, int) or release_id <= 0:
            raise ValueError(f"Rill release {rill_tag} has no numeric release id")
        with tempfile.TemporaryDirectory() as directory:
            evidence = rill_downloader(RILL_REPOSITORY, rill_tag, Path(directory))
        qualification_sha = evidence.get("qualificationSha256")
        sums_sha = evidence.get("sha256SumsSha256")
        if not isinstance(qualification_sha, str) or not SHA256.fullmatch(qualification_sha):
            raise ValueError("Rill qualification.json digest is not a SHA256")
        if not isinstance(sums_sha, str) or not SHA256.fullmatch(sums_sha):
            raise ValueError("Rill SHA256SUMS digest is not a SHA256")
        package_commit, package_version = validate_rill_qualification(
            evidence.get("qualification"), rill_tag
        )
        desired_rill = {
            "repository": RILL_REPOSITORY,
            "packageCommit": package_commit,
            "releaseTag": rill_tag,
            "releaseId": release_id,
            "qualificationSha256": qualification_sha,
            "sha256SumsSha256": sums_sha,
            "state": "locked",
            "reason": f"Stable {rill_tag} release verified automatically from its immutable qualification manifest.",
            "packageVersion": package_version,
            "channel": "stable",
        }
        if previous_rill.get("packageCommit") == package_commit:
            # An unchanged commit keeps the run identity that produced it; a
            # new commit invalidates that identity and drops the stale fields.
            for key in ("qualificationRunId", "qualificationRunAttempt"):
                if key in previous_rill:
                    desired_rill[key] = previous_rill[key]

    resolved = []
    for name, metadata in support.items():
        if name == RILL_RUNTIME:
            continue
        entry = packages.get(name) or {}
        repository, path = _declared_source(metadata, entry)
        # The lock entry wins when it declares a track; the support matrix is
        # the next authority (it declares "pinned" for packages whose version
        # is dictated per release series), and only then infer from the repo.
        track = entry.get("track") or metadata.get("track") or _default_track(metadata, repository)
        if track not in TRACKS:
            raise ValueError(f"package {name} uses unsupported track: {track!r}")
        if track == "pinned":
            continue
        if not isinstance(repository, str) or not repository or not isinstance(path, str) or not path:
            raise ValueError(
                f"package {name} must declare repository and path in the support matrix or source lock"
            )
        if track == "rill-release":
            if package_commit is None:
                raise ValueError(
                    f"package {name} requires track 'rill-release' but the "
                    "support matrix has no rill-runtime"
                )
            ref = package_commit
            version = version_reader(repository, ref, path)
        else:
            release = select_latest_stable(release_api(slug_from_repository(repository)))
            tag = release["tag_name"]
            ref = tag_resolver(repository, tag)
            if not isinstance(ref, str) or not SHA1.fullmatch(ref):
                raise ValueError(f"{name} tag {tag} did not resolve to an immutable commit")
            version = version_reader(repository, ref, path)
        resolved.append((name, repository, path, ref, version))

    # Apply only after every upstream identity has been resolved successfully.
    changes: list[str] = []
    if desired_rill is not None and _rill_identity(previous_rill) != _rill_identity(desired_rill):
        old_tag = previous_rill.get("releaseTag")
        changes.append(f"rill-runtime: {old_tag or 'unset'} -> {desired_rill['releaseTag']}")
        lock["rillRuntime"] = desired_rill
    for name, repository, path, ref, version in resolved:
        _apply_package(packages, name, repository, path, ref, version, changes)
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK, help="source lock path")
    parser.add_argument("--write", action="store_true", help="write the refreshed lock in place")
    args = parser.parse_args(argv)
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    changes = update(lock)
    if args.write:
        args.lock.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"changed": bool(changes), "changes": changes}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
