from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_cached_artifact.py"
SPEC = importlib.util.spec_from_file_location("verify_cached_artifact", SCRIPT)
verify_cached = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(verify_cached)

IDENTITY = {
    "package": "luci-app-cloudflare-ip",
    "openwrt_version": "25.12.6",
    "package_arch": "x86_64",
    "package_format": "apk",
    "sdk_tag": "x86-64-v25.12.6",
    "source_ref": "a" * 40,
    "expected_version": "2.6.2",
}


class VerifyCachedArtifactTests(unittest.TestCase):
    def make_cell(self, root: Path, *, package_bytes: bytes = b"artifact",
                  filename: str | None = None, evidence: dict | None = None) -> Path:
        cell = root / "out" / "25.12.6" / "x86_64"
        cell.mkdir(parents=True, exist_ok=True)
        name = filename or "luci-app-cloudflare-ip-2.6.2-r1.apk"
        (cell / name).write_bytes(package_bytes)
        identity = dict(IDENTITY)
        identity["packageSha256"] = hashlib.sha256(package_bytes).hexdigest()
        payload = {**identity, "package": IDENTITY["package"],
                   "openwrtVersion": IDENTITY["openwrt_version"],
                   "packageArch": IDENTITY["package_arch"],
                   "packageFormat": IDENTITY["package_format"],
                   "sdkTag": IDENTITY["sdk_tag"],
                   "sourceRef": IDENTITY["source_ref"],
                   "packageVersion": IDENTITY["expected_version"]}
        if evidence is not None:
            payload = evidence
        (cell / "luci-app-cloudflare-ip.build-evidence.json").write_text(json.dumps(payload))
        return cell

    def verify(self, root: Path):
        return verify_cached.verify(
            root / "out" / "25.12.6" / "x86_64",
            package=IDENTITY["package"],
            openwrt_version=IDENTITY["openwrt_version"],
            package_arch=IDENTITY["package_arch"],
            package_format=IDENTITY["package_format"],
            sdk_tag=IDENTITY["sdk_tag"],
            source_ref=IDENTITY["source_ref"],
            expected_version=IDENTITY["expected_version"],
        )

    def test_accepts_matching_cached_cell(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cell = self.make_cell(root)
            artifact = self.verify(root)
            self.assertEqual(artifact, cell / "luci-app-cloudflare-ip-2.6.2-r1.apk")

    def test_ipk_with_hyphenated_arch_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cell = root / "out" / "24.10.8" / "arm_cortex-a7_neon-vfpv4"
            cell.mkdir(parents=True)
            payload = b"ipk"
            (cell / "luci-app-openclash_0.48.002_all.ipk").write_bytes(payload)
            (cell / "luci-app-openclash.build-evidence.json").write_text(json.dumps({
                "package": "luci-app-openclash",
                "openwrtVersion": "24.10.8",
                "packageArch": "arm_cortex-a7_neon-vfpv4",
                "packageFormat": "ipk",
                "sdkTag": "ipq40xx-generic-v24.10.8",
                "sourceRef": "b" * 40,
                "packageVersion": "0.48.002",
                "packageSha256": hashlib.sha256(payload).hexdigest(),
            }))
            verify_cached.verify(
                cell, package="luci-app-openclash", openwrt_version="24.10.8",
                package_arch="arm_cortex-a7_neon-vfpv4", package_format="ipk",
                sdk_tag="ipq40xx-generic-v24.10.8", source_ref="b" * 40,
                expected_version="0.48.002",
            )

    def test_rejects_stale_source_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = {
                "package": IDENTITY["package"],
                "openwrtVersion": IDENTITY["openwrt_version"],
                "packageArch": IDENTITY["package_arch"],
                "packageFormat": IDENTITY["package_format"],
                "sdkTag": IDENTITY["sdk_tag"],
                "sourceRef": "c" * 40,  # stale commit
                "packageVersion": IDENTITY["expected_version"],
            }
            self.make_cell(root, evidence=evidence)
            with self.assertRaises(ValueError) as ctx:
                self.verify(root)
            self.assertIn("sourceRef mismatch", str(ctx.exception))

    def test_rejects_digest_mismatch_when_bytes_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cell = self.make_cell(root, package_bytes=b"original")
            (cell / "luci-app-cloudflare-ip-2.6.2-r1.apk").write_bytes(b"tampered")
            with self.assertRaises(ValueError) as ctx:
                self.verify(root)
            self.assertIn("packageSha256 mismatch", str(ctx.exception))

    def test_rejects_missing_or_multiple_package_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cell = self.make_cell(root)
            (cell / "luci-app-cloudflare-ip-2.6.2-r2.apk").write_bytes(b"duplicate")
            with self.assertRaises(ValueError) as ctx:
                self.verify(root)
            self.assertIn("exactly one", str(ctx.exception))

    def test_rejects_missing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cell = self.make_cell(root)
            (cell / "luci-app-cloudflare-ip.build-evidence.json").unlink()
            with self.assertRaises(ValueError) as ctx:
                self.verify(root)
            self.assertIn("missing build evidence", str(ctx.exception))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_cell(root)
            ok = subprocess.run(
                [sys.executable, str(SCRIPT), str(root / "out"),
                 "--package", IDENTITY["package"],
                 "--openwrt-version", IDENTITY["openwrt_version"],
                 "--package-arch", IDENTITY["package_arch"],
                 "--package-format", IDENTITY["package_format"],
                 "--sdk-tag", IDENTITY["sdk_tag"],
                 "--source-ref", IDENTITY["source_ref"],
                 "--expected-version", IDENTITY["expected_version"]],
                capture_output=True, text=True,
            )
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("verified", ok.stdout)

            bad = subprocess.run(
                [sys.executable, str(SCRIPT), str(root / "out"),
                 "--package", IDENTITY["package"],
                 "--openwrt-version", IDENTITY["openwrt_version"],
                 "--package-arch", IDENTITY["package_arch"],
                 "--package-format", IDENTITY["package_format"],
                 "--sdk-tag", IDENTITY["sdk_tag"],
                 "--source-ref", "d" * 40,
                 "--expected-version", IDENTITY["expected_version"]],
                capture_output=True, text=True,
            )
            self.assertEqual(bad.returncode, 1)
            self.assertIn("sourceRef mismatch", bad.stderr)


if __name__ == "__main__":
    unittest.main()
