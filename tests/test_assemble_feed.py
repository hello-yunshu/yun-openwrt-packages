from __future__ import annotations

import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/assemble_feed.py"
SPEC = importlib.util.spec_from_file_location("assemble_feed", SCRIPT)
assemble_feed = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(assemble_feed)


class AssembleFeedTests(unittest.TestCase):
    def fixture_identity(self, package):
        lock = json.loads((assemble_feed.ROOT / "metadata/source-lock.json").read_text())
        item = lock.get("rillRuntime", {}) if package == "rill-runtime" else lock.get("packages", {}).get(package, {})
        return item.get("releaseTag") or item.get("ref") or "fixture-sha", item.get("packageVersion") or "1.0"

    def test_stages_only_the_complete_matrix_under_release_scoped_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            output = root / "candidate"
            for (release, arch), packages in assemble_feed.expected_files().items():
                source_dir = artifacts / release / arch
                source_dir.mkdir(parents=True)
                for package, extension in packages:
                    source_ref, package_version = self.fixture_identity(package)
                    if package == "rill-runtime":
                        filename = f"rill-runtime-v{release}-{arch}{extension}"
                    elif extension == ".ipk":
                        filename = f"{package}_{package_version}_all.ipk"
                    else:
                        filename = f"{package}-{package_version}-r1.apk"
                    package_file = source_dir / filename
                    package_file.write_bytes(b"fixture")
                    (source_dir / f"{package}.build-evidence.json").write_text(json.dumps({
                        "package": package,
                        "openwrtVersion": release,
                        "packageArch": arch,
                        "packageFormat": "ipk" if extension == ".ipk" else "apk",
                        "packageSha256": hashlib.sha256(b"fixture").hexdigest(),
                        "sourceRef": source_ref,
                        "packageVersion": package_version,
                    }))
            count = assemble_feed.stage(artifacts, output)
            self.assertEqual(count, sum(len(v) for v in assemble_feed.expected_files().values()))
            cfi_version = self.fixture_identity("luci-app-cloudflare-ip")[1]
            manager_version = self.fixture_identity("rill-runtime-manager")[1]
            self.assertTrue((output / f"24.10.8/x86_64/luci-app-cloudflare-ip_{cfi_version}_all.ipk").is_file())
            self.assertTrue((output / f"25.12.6/mipsel_24kc/rill-runtime-manager-{manager_version}-r1.apk").is_file())
            rill_version = self.fixture_identity("rill-runtime")[0].removeprefix("v")
            # apk downloads by canonical <name>-<version>.apk; the staged tree
            # must not keep the imported multi-arch asset name.
            self.assertTrue((output / f"25.12.6/aarch64_cortex-a53/rill-runtime-{rill_version}.apk").is_file())
            self.assertFalse((output / "25.12.6/aarch64_cortex-a53/rill-runtime-v25.12.6-aarch64_cortex-a53.apk").exists())
            self.assertFalse((output / "24.10.8/mipsel_24kc/luci-app-performance-manager-all-1.0-r1.ipk").exists())
            candidate = json.loads((output / "candidate.json").read_text())
            self.assertTrue(candidate["publishable"])
            self.assertEqual(candidate["status"], "publishable-candidate")
            self.assertEqual(candidate["qualificationPolicy"], "automatic-build-verified")
            self.assertEqual(candidate["qualificationSummary"]["pending"], 0)
            self.assertGreater(candidate["qualificationSummary"]["build-verified"], 0)
            self.assertFalse(candidate["unqualifiedCells"])

    def test_accepts_real_hyphenated_arch_and_release_zero_apk_filenames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            output = root / "candidate"
            packages = {"luci-app-openclash", "luci-app-performance-manager-all"}
            for (release, arch), entries in assemble_feed.expected_files(packages).items():
                source_dir = artifacts / release / arch
                source_dir.mkdir(parents=True)
                for package, extension in entries:
                    source_ref, package_version = self.fixture_identity(package)
                    if extension == ".ipk":
                        filename = (
                            f"{package}_{package_version}-r7_{arch}.ipk"
                            if package == "luci-app-performance-manager-all"
                            else f"{package}_{package_version}_all.ipk"
                        )
                    elif package == "luci-app-openclash":
                        # Release 0 omits the -r suffix from the APK filename.
                        filename = f"{package}-{package_version}.apk"
                    else:
                        filename = f"{package}-{package_version}-r7.apk"
                    package_file = source_dir / filename
                    package_file.write_bytes(b"fixture")
                    (source_dir / f"{package}.build-evidence.json").write_text(json.dumps({
                        "package": package,
                        "openwrtVersion": release,
                        "packageArch": arch,
                        "packageFormat": "ipk" if extension == ".ipk" else "apk",
                        "packageSha256": hashlib.sha256(b"fixture").hexdigest(),
                        "sourceRef": source_ref,
                        "packageVersion": package_version,
                    }))
            assemble_feed.stage(artifacts, output, packages)
            self.assertTrue(
                (output / "24.10.8/aarch64_cortex-a53/luci-app-performance-manager-all_1.0.7-r7_aarch64_cortex-a53.ipk").is_file()
            )
            self.assertTrue((output / "25.12.6/x86_64/luci-app-openclash-0.48.002.apk").is_file())

    def test_rejects_missing_artifacts_before_staging_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "empty"
            artifacts.mkdir()
            output = root / "candidate"
            with self.assertRaisesRegex(ValueError, "incomplete package artifact matrix"):
                assemble_feed.stage(artifacts, output)
            self.assertFalse(output.exists())

    def test_rejects_locked_package_artifact_from_a_different_source_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            output = root / "candidate"
            packages = {"luci-app-nginx-manager"}
            for (release, arch), entries in assemble_feed.expected_files(packages).items():
                source_dir = artifacts / release / arch
                source_dir.mkdir(parents=True)
                for package, extension in entries:
                    source_ref, package_version = self.fixture_identity(package)
                    filename = f"{package}_{package_version}_all.ipk" if extension == ".ipk" else f"{package}-{package_version}-r1.apk"
                    artifact = source_dir / filename
                    artifact.write_bytes(b"fixture")
                    (source_dir / f"{package}.build-evidence.json").write_text(json.dumps({
                        "package": package,
                        "openwrtVersion": release,
                        "packageArch": arch,
                        "packageFormat": "ipk" if extension == ".ipk" else "apk",
                        "packageSha256": hashlib.sha256(b"fixture").hexdigest(),
                        "sourceRef": "f" * 40 if release == "24.10.8" and arch == "x86_64" else source_ref,
                        "packageVersion": package_version,
                    }))
            with self.assertRaisesRegex(ValueError, "sourceRef differs from immutable source lock"):
                assemble_feed.stage(artifacts, output, packages)
            self.assertFalse(output.exists())

    def test_partial_candidate_cannot_be_marked_publishable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            output = root / "candidate"
            packages = {"luci-app-nginx-manager"}
            for (release, arch), entries in assemble_feed.expected_files(packages).items():
                source_dir = artifacts / release / arch
                source_dir.mkdir(parents=True)
                for package, extension in entries:
                    source_ref, package_version = self.fixture_identity(package)
                    if package == "rill-runtime":
                        filename = f"rill-runtime-v{release}-{arch}{extension}"
                    elif extension == ".ipk":
                        filename = f"{package}_{package_version}-r1_all.ipk"
                    else:
                        filename = f"{package}-{package_version}-r1.apk"
                    package_file = source_dir / filename
                    package_file.write_bytes(b"fixture")
                    (source_dir / f"{package}.build-evidence.json").write_text(json.dumps({
                        "package": package,
                        "openwrtVersion": release,
                        "packageArch": arch,
                        "packageFormat": "ipk" if extension == ".ipk" else "apk",
                        "packageSha256": hashlib.sha256(b"fixture").hexdigest(),
                        "sourceRef": source_ref,
                        "packageVersion": package_version,
                    }))
            assemble_feed.stage(artifacts, output, packages)
            candidate = json.loads((output / "candidate.json").read_text())
            self.assertEqual(candidate["status"], "partial-candidate")
            self.assertFalse(candidate["publishable"])
            self.assertIn("luci-app-performance-manager-all", candidate["omittedPackages"])


if __name__ == "__main__":
    unittest.main()
