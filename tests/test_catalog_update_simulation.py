"""6-Pre-C local update / rollback tests; never requests a network resource."""
import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("updater", ROOT / "scripts" / "simulate_catalog_update.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SOURCE = json.loads((ROOT / "catalog" / "unity-kb-catalog.json").read_text(encoding="utf-8"))


def candidate(version, **changes):
    obj = copy.deepcopy(SOURCE)
    obj.update(schema_version=1, catalog_status="stable", catalog_version=version)
    obj.update(changes)
    raw = json.dumps(obj, sort_keys=True).encode("utf-8")
    meta = {"sha256": hashlib.sha256(raw).hexdigest(),
            "schema_version": 1, "catalog_version": version,
            "catalog_status": "stable", "catalog_file": "catalog/unity-kb-catalog.json"}
    return raw, meta


class TestCatalogUpdaterSimulation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="unity-6-pre-c-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw1, self.meta1 = candidate("0.1.0")
        self.raw2, self.meta2 = candidate("0.2.0")
        self.raw3, self.meta3 = candidate("0.3.0")

    def seed(self):
        self.assertEqual(m.update(self.root, self.raw1, self.meta1), "0.1.0")

    def active(self):
        return m.read_envelope(self.root / "active.json")

    def assert_rejected_unchanged(self, raw, meta, *, fragment=None, fault=None):
        before = self.active()
        with self.assertRaises(m.UpdateRejected) as ctx:
            m.update(self.root, raw, meta, fault=fault)
        if fragment:
            self.assertIn(fragment, str(ctx.exception))
        self.assertEqual(self.active(), before)

    def test_c01_first_install_valid_synthetic_stable(self):
        self.seed()
        self.assertEqual(self.active()["version"], "0.1.0")

    def test_c02_upgrade_preserves_previous_cache(self):
        self.seed()
        self.assertEqual(m.update(self.root, self.raw2, self.meta2), "0.2.0")
        self.assertEqual(self.active()["version"], "0.2.0")
        self.assertEqual(m.read_envelope(self.root / "previous.json")["version"], "0.1.0")

    def test_c03_sha256_mismatch_rejected(self):
        self.seed()
        raw = self.raw2.replace(b'"0.2.0"', b'"0.4.0"')
        self.assert_rejected_unchanged(raw, self.meta2, fragment="SHA-256 mismatch")

    def test_c04_truncated_download_rejected(self):
        self.seed()
        raw = self.raw2[:len(self.raw2)//2]
        meta = dict(self.meta2, sha256=hashlib.sha256(raw).hexdigest())
        self.assert_rejected_unchanged(raw, meta, fragment="invalid or truncated JSON")

    def test_c05_offline_download_failure_keeps_cache(self):
        self.seed()
        self.assert_rejected_unchanged(self.raw2, self.meta2,
                                      fragment="download interrupted", fault="download_interrupted")

    def test_c06_before_commit_failure_keeps_cache(self):
        self.seed()
        self.assert_rejected_unchanged(self.raw2, self.meta2,
                                      fragment="before commit", fault="before_commit")

    def test_c07_after_commit_rollback_restores_active(self):
        self.seed()
        self.assert_rejected_unchanged(self.raw2, self.meta2,
                                      fragment="rollback restored", fault="after_commit")

    def test_c08_downgrade_rejected(self):
        self.seed()
        m.update(self.root, self.raw2, self.meta2)
        self.assert_rejected_unchanged(self.raw1, self.meta1, fragment="downgrade rejected")

    def test_c09_same_version_replacement_rejected(self):
        self.seed()
        self.assert_rejected_unchanged(self.raw1, self.meta1, fragment="same-version")

    def test_c10_manifest_catalog_version_mismatch(self):
        self.seed()
        meta = dict(self.meta2, catalog_version="0.4.0")
        self.assert_rejected_unchanged(self.raw2, meta, fragment="version mismatch")

    def test_c11_invalid_schema_rejected(self):
        self.seed()
        meta = dict(self.meta2, schema_version=True)
        self.assert_rejected_unchanged(self.raw2, meta, fragment="unsupported metadata schema")

    def test_c12_draft_release_rejected(self):
        self.seed()
        raw, meta = candidate("0.2.0", catalog_status="draft")
        self.assert_rejected_unchanged(raw, meta, fragment="stable candidates")

    def test_c13_enabled_matching_rejected(self):
        self.seed()
        payload = copy.deepcopy(SOURCE)
        payload["articles"][0]["matching"]["enabled"] = True
        raw, meta = candidate("0.2.0", articles=payload["articles"])
        self.assert_rejected_unchanged(raw, meta, fragment="matching must remain disabled")

    def test_c14_invalid_json_duplicate_key_rejected(self):
        self.seed()
        raw = self.raw2.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1', 1)
        meta = dict(self.meta2, sha256=hashlib.sha256(raw).hexdigest())
        self.assert_rejected_unchanged(raw, meta, fragment="duplicate JSON key")

    def test_c15_corrupted_active_recovers_previous(self):
        self.seed()
        m.update(self.root, self.raw2, self.meta2)
        active = self.root / "active.json"
        obj = json.loads(active.read_text(encoding="utf-8"))
        obj["catalog"]["description"] = "tampered"
        active.write_text(json.dumps(obj), encoding="utf-8")
        self.assertEqual(m.recover(self.root)["version"], "0.1.0")
        self.assertEqual(self.active()["version"], "0.1.0")

    def test_c16_without_previous_corruption_fails_closed(self):
        self.seed()
        (self.root / "active.json").write_text("not-json", encoding="utf-8")
        with self.assertRaisesRegex(m.UpdateRejected, "no last-known-good cache"):
            m.recover(self.root)

    def test_c17_install_failure_rolls_back_to_no_active(self):
        with self.assertRaisesRegex(m.UpdateRejected, "rollback restored"):
            m.update(self.root, self.raw1, self.meta1, fault="after_commit")
        self.assertFalse((self.root / "active.json").exists())

    def test_c18_damaged_previous_does_not_masquerade_as_valid(self):
        self.seed()
        m.update(self.root, self.raw2, self.meta2)
        (self.root / "previous.json").write_text("{}", encoding="utf-8")
        (self.root / "active.json").write_text("corrupted", encoding="utf-8")
        with self.assertRaises(m.UpdateRejected):
            m.recover(self.root)

    def test_c19_invalid_catalog_path_rejected(self):
        self.seed()
        meta = dict(self.meta2, catalog_file="../catalog.json")
        self.assert_rejected_unchanged(self.raw2, meta, fragment="Catalog path")

    def test_c20_experiment_does_not_change_source_catalog(self):
        self.seed()
        self.assertEqual(SOURCE["catalog_status"], "draft")
        self.assertTrue(all(a["matching"]["enabled"] is False for a in SOURCE["articles"]))
        self.assertEqual(json.loads((ROOT / "catalog" / "unity-kb-catalog.json").read_text(encoding="utf-8")), SOURCE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
