from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class IpkIndexSignatureContractTests(unittest.TestCase):
    def test_opkg_signature_covers_downloaded_gzip_index(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        ipk_block = workflow.split('if [ "$PACKAGE_FORMAT" = ipk ]; then', 1)[1].split(
            'elif [ "$PACKAGE_FORMAT" = apk ]; then', 1
        )[0]

        self.assertIn("gzip -9nc Packages > Packages.gz", ipk_block)
        self.assertIn("gzip -dc Packages.gz | cmp - Packages", ipk_block)
        self.assertIn("usign -S -m Packages.gz -s", ipk_block)
        self.assertIn("usign -V -m Packages.gz -p", ipk_block)
        self.assertNotIn("usign -S -m Packages ", ipk_block)
        self.assertNotIn("usign -V -m Packages ", ipk_block)


if __name__ == "__main__":
    unittest.main()
