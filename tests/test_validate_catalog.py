"""5-E negative regression tests. Operates only on temporary copies of the catalog."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_catalog.py"
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
CATALOG = json.loads((ROOT / "catalog" / "unity-kb-catalog.json").read_text(encoding="utf-8"))


def run_validator(catalog, manifest=None):
    with tempfile.TemporaryDirectory(prefix="unity-kb-validator-") as directory:
        root = Path(directory)
        (root / "scripts").mkdir()
        (root / "catalog").mkdir()
        (root / "scripts" / "validate_catalog.py").write_bytes(SCRIPT.read_bytes())
        (root / "manifest.json").write_text(json.dumps(manifest or MANIFEST), encoding="utf-8")
        (root / "catalog" / "unity-kb-catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(root / "scripts" / "validate_catalog.py")],
            text=True, capture_output=True, timeout=30, check=False
        )
        return proc.returncode, proc.stdout + proc.stderr


class TestCatalogValidator(unittest.TestCase):
    def test_t01_normal_catalog_pass(self):
        code, log = run_validator(CATALOG)
        self.assertEqual(code, 0, log)
        self.assertIn("VALIDATION PASSED", log)
        self.assertIn("Checked 3 KB articles", log)

    def test_t02_reversed_oe_range_rejected(self):
        data = copy.deepcopy(CATALOG)
        article = next(x for x in data["articles"] if x["kb_id"] == "000200921")
        article["oe_rules"][0]["min_version"] = "5.3.0.0.5.120"
        code, log = run_validator(data)
        self.assertNotEqual(code, 0, log)
        self.assertIn("min_version exceeds max_version", log)

    def test_t03_duplicate_kb_id_rejected(self):
        data = copy.deepcopy(CATALOG)
        data["articles"].append(copy.deepcopy(data["articles"][0]))
        code, log = run_validator(data)
        self.assertNotEqual(code, 0, log)
        self.assertIn("duplicate KB ID 000216765", log)

    def test_t04_bad_verification_status_rejected(self):
        data = copy.deepcopy(CATALOG)
        data["articles"][0]["verification_status"] = "verified_typo"
        code, log = run_validator(data)
        self.assertNotEqual(code, 0, log)
        self.assertIn("invalid verification_status", log)

    def test_t05_enabled_matching_rejected(self):
        data = copy.deepcopy(CATALOG)
        data["articles"][0]["matching"]["enabled"] = True
        code, log = run_validator(data)
        self.assertNotEqual(code, 0, log)
        self.assertIn("matching must remain disabled", log)

    def test_t06_incident_match_status_rejected(self):
        data = copy.deepcopy(CATALOG)
        data["articles"][0]["matching"]["match_status"] = "STRONG_MATCH"
        code, log = run_validator(data)
        self.assertNotEqual(code, 0, log)
        self.assertIn("incident match_status belongs in Analyzer", log)

    def test_t07_manual_review_without_reason_rejected(self):
        data = copy.deepcopy(CATALOG)
        article = next(x for x in data["articles"] if x["kb_id"] == "000191697")
        article["oe_rules"][0].pop("reason")
        code, log = run_validator(data)
        self.assertNotEqual(code, 0, log)
        self.assertIn("manual review reason is required", log)

    def test_t08_mismatched_kb_url_rejected(self):
        data = copy.deepcopy(CATALOG)
        data["articles"][0]["url"] = data["articles"][0]["url"].replace("000216765", "000000001")
        code, log = run_validator(data)
        self.assertNotEqual(code, 0, log)
        self.assertIn("invalid Dell URL or KB ID mismatch", log)

    def test_t09_original_catalog_still_passes(self):
        code, log = run_validator(copy.deepcopy(CATALOG))
        self.assertEqual(code, 0, log)
        self.assertIn("VALIDATION PASSED", log)


if __name__ == "__main__":
    unittest.main(verbosity=2)
