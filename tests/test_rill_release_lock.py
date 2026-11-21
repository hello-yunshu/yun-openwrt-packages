from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_rill_release.py"
SPEC = importlib.util.spec_from_file_location("verify_rill_release", SCRIPT)
verify_rill_release = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(verify_rill_release)


class RillReleaseLockTests(unittest.TestCase):
    def test_rejects_invalid_qualification_digest_before_using_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "invalid locked qualification SHA256"):
                verify_rill_release.verify(
                    Path(tmp), "v1.5.6-r1", "1234", "not-a-sha", "0" * 64, "a" * 40
                )

    def test_rejects_unlocked_or_missing_release_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "qualification.json is missing"):
                verify_rill_release.verify(
                    Path(tmp), "v1.5.6-r1", "1234", "0" * 64, "1" * 64, "a" * 40
                )


if __name__ == "__main__":
    unittest.main()
