from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / f"scripts/{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


validator = load_script("validate_mainstream_support")
assembler = load_script("assemble_feed")


class QualificationLevelTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "metadata/mainstream-support.json").read_text())

    def supported_row(self, data):
        return next(row for row in data["qualificationMatrix"] if row["status"] == "pending")

    def mark_row(self, row, level):
        row["status"] = level
        row["checks"] = {
            "build": "passed",
            "dependencyResolution": "passed",
            "signature": "passed",
            "cleanInstall": "passed",
            "upgrade": "passed",
            "runtime": "not-evaluated-device" if level == "build-install-qualified" else "passed",
        }
        row["evidence"] = {
            "sourceCommit": "a" * 40,
            "buildRun": "https://example.invalid/build/123",
            "buildEvidence": "https://example.invalid/build-evidence.json",
            "signatureEvidence": "https://example.invalid/signature-evidence.json",
            "dependencyEvidence": "https://example.invalid/dependency-evidence.json",
            "installEvidence": "https://example.invalid/install-evidence.json",
            "upgradeEvidence": "https://example.invalid/upgrade-evidence.json",
        }
        if level == "device-runtime-qualified":
            row["evidence"]["runtimeEvidence"] = "https://example.invalid/runtime-evidence.json"

    def test_real_matrix_remains_pending(self):
        validator.validate(copy.deepcopy(self.data))
        self.assertEqual({row["status"] for row in self.data["qualificationMatrix"]}, {"pending", "unsupported"})

    def test_build_install_level_does_not_require_or_claim_device_runtime(self):
        row = self.supported_row(self.data)
        self.mark_row(row, "build-install-qualified")
        validator.validate(self.data)

    def test_device_runtime_level_requires_runtime_check_and_evidence(self):
        row = self.supported_row(self.data)
        self.mark_row(row, "device-runtime-qualified")
        validator.validate(self.data)

    def test_build_install_level_cannot_claim_runtime_passed(self):
        row = self.supported_row(self.data)
        self.mark_row(row, "build-install-qualified")
        row["checks"]["runtime"] = "passed"
        with self.assertRaisesRegex(ValueError, "leave device Runtime unevaluated"):
            validator.validate(self.data)

    def test_device_runtime_level_requires_runtime_evidence(self):
        row = self.supported_row(self.data)
        self.mark_row(row, "device-runtime-qualified")
        del row["evidence"]["runtimeEvidence"]
        with self.assertRaisesRegex(ValueError, "without required evidence"):
            validator.validate(self.data)

    def test_ambiguous_qualified_status_is_rejected(self):
        row = self.supported_row(self.data)
        row["status"] = "qualified"
        with self.assertRaisesRegex(ValueError, "matrix status disagrees"):
            validator.validate(self.data)

    def test_candidate_accepts_build_install_rows_but_retains_each_level(self):
        selected = set(self.data["packages"])
        for row in self.data["qualificationMatrix"]:
            if row["status"] == "pending":
                self.mark_row(row, "build-install-qualified")
        levels, pending, counts = assembler.qualification_summary(self.data, selected)
        self.assertEqual(pending, [])
        self.assertEqual(counts["build-install-qualified"], 108)
        self.assertEqual(counts["unsupported"], 4)
        self.assertTrue(all(
            row["runtimeCheck"] == "not-evaluated-device"
            for row in levels if row["level"] == "build-install-qualified"
        ))

    def test_candidate_never_treats_pending_runtime_as_qualified(self):
        selected = set(self.data["packages"])
        row = self.supported_row(self.data)
        self.mark_row(row, "build-install-qualified")
        levels, pending, counts = assembler.qualification_summary(self.data, selected)
        self.assertEqual(len(pending), 107)
        self.assertEqual(counts["build-install-qualified"], 1)
        self.assertEqual(counts["pending"], 107)

    def test_run_evidence_derives_build_verified_without_claiming_more(self):
        selected = set(self.data["packages"])
        cells = {
            (row["package"], row["openwrtVersion"], row["packageArch"])
            for row in self.data["qualificationMatrix"]
            if row["status"] == "pending"
        }
        levels, pending, counts = assembler.qualification_summary(self.data, selected, cells)
        self.assertEqual(pending, [])
        self.assertEqual(counts["pending"], 0)
        self.assertEqual(counts["build-verified"], len(cells))
        self.assertEqual(counts["unsupported"], 4)
        self.assertEqual(counts["build-install-qualified"], 0)
        self.assertEqual(counts["device-runtime-qualified"], 0)

    def test_new_package_without_qualification_rows_is_derived_at_assembly(self):
        self.data["packages"]["luci-app-brand-new"] = {
            "repository": "https://github.com/hello-yunshu/luci-app-brand-new.git",
            "path": "package/luci-app-brand-new",
            "packageArch": "all",
            "architectures": ["x86_64"],
            "qualificationState": "pending",
        }
        validator.validate(self.data)
        selected = set(self.data["packages"])
        levels, pending, counts = assembler.qualification_summary(self.data, selected)
        new_cells = [row for row in levels if row["package"] == "luci-app-brand-new"]
        self.assertEqual({row["level"] for row in new_cells}, {"pending", "unsupported"})
        self.assertEqual(len([row for row in new_cells if row["level"] == "unsupported"]), 12)
        self.assertEqual(counts["pending"], 110)
        self.assertEqual(counts["unsupported"], 16)
        self.assertEqual(len([row for row in pending if row["package"] == "luci-app-brand-new"]), 2)

        verified = {
            (row["package"], row["openwrtVersion"], row["packageArch"])
            for row in levels if row["level"] == "pending"
        }
        _, still_pending, counts = assembler.qualification_summary(self.data, selected, verified)
        self.assertEqual(still_pending, [])
        self.assertEqual(counts["build-verified"], 110)
        self.assertEqual(counts["pending"], 0)


if __name__ == "__main__":
    unittest.main()
