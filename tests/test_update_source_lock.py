from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/update_source_lock.py"
SPEC = importlib.util.spec_from_file_location("update_source_lock", SCRIPT)
update_source_lock = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(update_source_lock)


def commit_for(tag: str) -> str:
    return hashlib.sha1(tag.encode("utf-8")).hexdigest()


class FakeUpstream:
    """Deterministic stand-in for the GitHub release, git, and download calls."""

    standard_tag = "v2.0.0"
    standard_version = "2.0.0"
    manager_version = "1.0.0"
    rill_tag = "v1.5.6-r8"
    rill_release_id = 453531268
    qualification_sha = "1" * 64
    sums_sha = "2" * 64

    def __init__(self):
        self.rill_commit = commit_for(self.rill_tag)
        self.resolved_tags = []
        self.qualification = {
            "schemaVersion": 4,
            "qualificationState": "automated-qualification",
            "releaseEligible": True,
            "packageCommit": self.rill_commit,
            "package": {"name": "rill-runtime", "version": "1.5.6", "release": "8"},
        }

    def releases(self, slug):
        if slug == update_source_lock.RILL_SLUG:
            return [
                {"tag_name": "v9.9.9-r1", "draft": False, "prerelease": True, "id": 9},
                {"tag_name": self.rill_tag, "draft": False, "prerelease": False, "id": self.rill_release_id},
            ]
        return [
            {"tag_name": "v9.9.9", "draft": False, "prerelease": True, "id": 1},
            {"tag_name": "v9.9.8", "draft": True, "prerelease": False, "id": 2},
            {"tag_name": self.standard_tag, "draft": False, "prerelease": False, "id": 3},
        ]

    def resolve(self, repository, tag):
        self.resolved_tags.append(tag)
        if tag == self.rill_tag:
            return self.rill_commit
        return commit_for(tag)

    def read_version(self, repository, commit, path):
        if path == "package/rill-runtime-manager":
            return self.manager_version
        return self.standard_version

    def download(self, repository_url, tag, directory):
        return {
            "qualificationSha256": self.qualification_sha,
            "sha256SumsSha256": self.sums_sha,
            "qualification": self.qualification,
        }


class MatchingLockUpstream:
    """Fake upstream whose answers reproduce the current lock exactly."""

    def __init__(self, lock):
        self.packages = lock["packages"]
        self.rill = lock["rillRuntime"]
        self.stable_tag = "v1.0.0"

    def releases(self, slug):
        if slug == update_source_lock.RILL_SLUG:
            return [
                {"tag_name": "v9.9.9-r1", "draft": False, "prerelease": True, "id": 1},
                {"tag_name": self.rill["releaseTag"], "draft": False, "prerelease": False,
                 "id": self.rill["releaseId"]},
            ]
        return [{"tag_name": self.stable_tag, "draft": False, "prerelease": False, "id": 2}]

    def resolve(self, repository, tag):
        for entry in self.packages.values():
            if entry["repository"] == repository:
                return entry["ref"]
        raise AssertionError(f"unexpected repository: {repository}")

    def read_version(self, repository, commit, path):
        for entry in self.packages.values():
            if entry["ref"] == commit and entry.get("path") == path:
                return entry["packageVersion"]
        raise AssertionError(f"unexpected package source: {commit} {path}")

    def download(self, repository_url, tag, directory):
        release = self.rill["releaseTag"].rsplit("-r", 1)[1]
        return {
            "qualificationSha256": self.rill["qualificationSha256"],
            "sha256SumsSha256": self.rill["sha256SumsSha256"],
            "qualification": {
                "schemaVersion": 4,
                "qualificationState": "automated-qualification",
                "releaseEligible": True,
                "packageCommit": self.rill["packageCommit"],
                "package": {
                    "name": "rill-runtime",
                    "version": self.rill["packageVersion"],
                    "release": release,
                },
            },
        }


def apply_update(lock, upstream, support_packages=None, support_path=None):
    kwargs = {
        "release_api": upstream.releases,
        "tag_resolver": upstream.resolve,
        "version_reader": upstream.read_version,
        "rill_downloader": upstream.download,
    }
    if support_packages is not None:
        kwargs["support_packages"] = support_packages
    if support_path is not None:
        kwargs["support_path"] = support_path
    return update_source_lock.update(lock, **kwargs)


class UpdateSourceLockTests(unittest.TestCase):
    def test_latest_stable_release_ignores_draft_and_prerelease(self):
        upstream = FakeUpstream()
        lock = {
            "schemaVersion": 1,
            "packages": {
                "luci-app-nginx-manager": {
                    "repository": "https://github.com/hello-yunshu/luci-app-nginx-manager.git",
                    "path": ".",
                    "ref": "0" * 40,
                    "packageVersion": "0.0.0",
                    "state": "locked",
                }
            },
        }
        changes = apply_update(
            lock, upstream, support_packages={"luci-app-nginx-manager": {}}
        )
        entry = lock["packages"]["luci-app-nginx-manager"]
        self.assertEqual(entry["ref"], commit_for(upstream.standard_tag))
        self.assertEqual(entry["packageVersion"], upstream.standard_version)
        self.assertEqual(entry["state"], "locked")
        self.assertNotIn("v9.9.9", upstream.resolved_tags)
        self.assertNotIn("v9.9.8", upstream.resolved_tags)
        self.assertTrue(changes)

    def test_rill_runtime_lock_binds_manager_and_records_evidence(self):
        upstream = FakeUpstream()
        lock = {
            "schemaVersion": 1,
            "packages": {
                "rill-runtime-manager": {
                    "repository": "https://github.com/hello-yunshu/rill-openwrt-packages.git",
                    "path": "package/rill-runtime-manager",
                    "state": "pending",
                }
            },
            "rillRuntime": {},
        }
        support = {
            "rill-runtime-manager": {"rillRuntime": "manager-only"},
            "rill-runtime": {"rillRuntime": "provider"},
        }
        apply_update(lock, upstream, support_packages=support)
        rill = lock["rillRuntime"]
        self.assertEqual(rill["repository"], update_source_lock.RILL_REPOSITORY)
        self.assertEqual(rill["packageCommit"], upstream.rill_commit)
        self.assertEqual(rill["releaseTag"], upstream.rill_tag)
        self.assertEqual(rill["releaseId"], upstream.rill_release_id)
        self.assertEqual(rill["qualificationSha256"], upstream.qualification_sha)
        self.assertEqual(rill["sha256SumsSha256"], upstream.sums_sha)
        self.assertEqual(rill["packageVersion"], "1.5.6")
        self.assertEqual(rill["channel"], "stable")
        self.assertEqual(rill["state"], "locked")
        self.assertNotIn("qualificationRunId", rill)
        self.assertNotIn("qualificationRunAttempt", rill)
        manager = lock["packages"]["rill-runtime-manager"]
        self.assertEqual(manager["ref"], rill["packageCommit"])
        self.assertEqual(manager["packageVersion"], upstream.manager_version)

    def test_no_changes_when_lock_matches_upstream(self):
        lock = json.loads(update_source_lock.DEFAULT_LOCK.read_text(encoding="utf-8"))
        upstream = MatchingLockUpstream(lock)
        changes = apply_update(lock, upstream)
        self.assertEqual(changes, [])

    def test_rejects_qualification_manifest_with_mismatched_release_tag(self):
        upstream = FakeUpstream()
        upstream.qualification = {
            "schemaVersion": 4,
            "qualificationState": "automated-qualification",
            "releaseEligible": True,
            "packageCommit": upstream.rill_commit,
            "package": {"name": "rill-runtime", "version": "9.9.9", "release": "1"},
        }
        lock = {"schemaVersion": 1, "packages": {}, "rillRuntime": {}}
        with self.assertRaisesRegex(ValueError, "release tag does not match"):
            apply_update(
                lock, upstream, support_packages={"rill-runtime": {"rillRuntime": "provider"}}
            )

    def test_new_support_package_is_resolved_without_a_lock_template(self):
        upstream = FakeUpstream()
        lock = {"schemaVersion": 1, "packages": {}}
        support = {
            "luci-app-brand-new": {
                "repository": "https://github.com/example/luci-app-brand-new.git",
                "path": "package/luci-app-brand-new",
            }
        }
        changes = apply_update(lock, upstream, support_packages=support)
        entry = lock["packages"]["luci-app-brand-new"]
        self.assertEqual(entry["repository"], "https://github.com/example/luci-app-brand-new.git")
        self.assertEqual(entry["path"], "package/luci-app-brand-new")
        self.assertEqual(entry["ref"], commit_for(upstream.standard_tag))
        self.assertEqual(entry["packageVersion"], upstream.standard_version)
        self.assertEqual(entry["state"], "locked")
        self.assertTrue(changes)

    def test_support_matrix_pinned_track_never_touches_upstream_releases(self):
        class NoContactUpstream:
            def releases(self, slug):
                raise AssertionError("pinned package must not list upstream releases")

            def resolve(self, repository, tag):
                raise AssertionError("pinned package must not resolve tags")

            def read_version(self, repository, commit, path):
                raise AssertionError("pinned package must not read upstream versions")

            def download(self, repository_url, tag, directory):
                raise AssertionError("pinned package must not download Rill evidence")

        lock = {
            "schemaVersion": 1,
            "packages": {
                "nginx-quic": {
                    "repository": "https://github.com/hello-yunshu/yun-openwrt-packages.git",
                    "path": "local-packages/nginx-quic",
                    "ref": "1" * 40,
                    "packageVersion": "1.30.7",
                    "state": "locked",
                }
            },
        }
        changes = apply_update(
            lock,
            NoContactUpstream(),
            support_packages={"nginx-quic": {"track": "pinned"}},
        )
        self.assertEqual(changes, [])
        self.assertEqual(lock["packages"]["nginx-quic"]["ref"], "1" * 40)

    def test_rejects_source_identity_drift_between_support_and_lock(self):
        upstream = FakeUpstream()
        lock = {
            "schemaVersion": 1,
            "packages": {
                "luci-app-drift": {
                    "repository": "https://github.com/hello-yunshu/luci-app-drift.git",
                    "path": "package/luci-app-drift",
                    "state": "pending",
                }
            },
        }
        support = {
            "luci-app-drift": {
                "repository": "https://github.com/someone-else/luci-app-drift.git",
                "path": "package/luci-app-drift",
            }
        }
        with self.assertRaisesRegex(ValueError, "disagrees between the support matrix"):
            apply_update(lock, upstream, support_packages=support)

    def test_support_package_missing_from_lock_fails_closed(self):
        upstream = FakeUpstream()
        lock = {"schemaVersion": 1, "packages": {}}
        with self.assertRaisesRegex(ValueError, "luci-app-unlocked is missing"):
            apply_update(lock, upstream, support_packages={"luci-app-unlocked": {}})


if __name__ == "__main__":
    unittest.main()
