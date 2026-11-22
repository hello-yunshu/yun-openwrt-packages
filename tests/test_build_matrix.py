from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_matrix.py"
SPEC = importlib.util.spec_from_file_location("build_matrix", SCRIPT)
build_matrix = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(build_matrix)


class BuildMatrixTests(unittest.TestCase):
    def test_matrix_uses_exact_release_format_pairs(self):
        rows = build_matrix.generate("available-only")
        self.assertEqual({(row["openwrtVersion"], row["packageFormat"]) for row in rows}, {
            ("24.10.8", "ipk"), ("25.12.6", "apk")
        })

    def test_full_scope_fails_closed_while_source_locks_are_pending(self):
        lock = json.loads(build_matrix.SOURCE_LOCK.read_text())
        lock["packages"]["luci-app-openclash"]["state"] = "pending"
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "source-lock.json"
            lock_path.write_text(json.dumps(lock))
            original = build_matrix.SOURCE_LOCK
            build_matrix.SOURCE_LOCK = lock_path
            try:
                with self.assertRaisesRegex(ValueError, "required source locks are pending"):
                    build_matrix.generate("all-required")
            finally:
                build_matrix.SOURCE_LOCK = original

    def test_available_only_scope_contains_only_locked_sources(self):
        rows = build_matrix.generate("available-only")
        lock = json.loads(build_matrix.SOURCE_LOCK.read_text())
        self.assertEqual({row["package"] for row in rows}, {
            "luci-app-nginx-manager", "luci-app-upnp-nat-relay", "luci-app-openclash",
            "luci-app-cloudflare-ip", "luci-app-performance-manager-all", "rill-runtime-manager",
            "rill-runtime",
        })
        self.assertTrue(all(
            len(row["sourceRef"]) == 40
            if row["package"] != "rill-runtime"
            else row["sourceRef"] == lock["rillRuntime"]["releaseTag"]
            for row in rows
        ))
        expected_versions = {
            name: entry["packageVersion"] for name, entry in lock["packages"].items()
        }
        expected_versions["rill-runtime"] = lock["rillRuntime"]["packageVersion"]
        self.assertEqual({row["package"]: row["expectedPackageVersion"] for row in rows}, expected_versions)

    def test_runtime_manager_is_locked_to_the_rill_source_commit(self):
        rows = build_matrix.generate("available-only")
        manager_rows = [row for row in rows if row["package"] == "rill-runtime-manager"]
        self.assertTrue(manager_rows)
        lock = json.loads(build_matrix.SOURCE_LOCK.read_text())
        manager_ref = lock["packages"]["rill-runtime-manager"]["ref"]
        self.assertEqual({row["sourceRef"] for row in manager_rows}, {manager_ref})
        for package in ("luci-app-cloudflare-ip", "luci-app-performance-manager-all"):
            consumer_rows = [row for row in rows if row["package"] == package]
            self.assertTrue(consumer_rows)
            self.assertEqual({row["rillSourceCommit"] for row in consumer_rows}, {manager_ref})

    def test_native_architecture_scope_is_reflected_in_manifest(self):
        data = build_matrix.load_matrix()
        for package in ("rill-runtime", "luci-app-performance-manager-all"):
            self.assertEqual(
                set(data["packages"][package]["architectures"]),
                {
                    "x86_64", "aarch64_generic", "aarch64_cortex-a53",
                    "aarch64_cortex-a72", "aarch64_cortex-a76",
                    "arm_cortex-a7_neon-vfpv4",
                },
            )

    def test_candidate_matrix_size_and_signing_axes(self):
        rows = build_matrix.generate("available-only")
        self.assertEqual(len(rows), 94)
        self.assertEqual(len(build_matrix.index_matrix("available-only")), 14)

    def test_noarch_cfi_and_manager_include_mips(self):
        data = build_matrix.load_matrix()
        for package in ("luci-app-cloudflare-ip", "rill-runtime-manager"):
            self.assertIn("mipsel_24kc", data["packages"][package]["architectures"])

    def test_sdk_tag_is_release_and_target_pinned(self):
        rows = build_matrix.generate("available-only")
        self.assertTrue(all(row["sdkTag"].endswith("-v" + row["openwrtVersion"]) for row in rows))

    def test_runtime_rows_are_imports_from_qualified_release_assets(self):
        data = build_matrix.load_matrix()
        self.assertEqual(len(data["packages"]["rill-runtime"]["architectures"]), 6)


if __name__ == "__main__":
    unittest.main()
