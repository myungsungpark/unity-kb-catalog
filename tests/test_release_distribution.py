"""Release packaging and update tests; hermetic, no network or production key."""
import json
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.release_catalog import build
from scripts.catalog_updater import ASSETS, install_from_assets, verify_assets


class TestSignedCatalog(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.root = Path(self.d.name)
        self.catalog = self.root / "candidate.json"
        source = json.loads((Path(__file__).resolve().parents[1] / "catalog/unity-kb-catalog.json").read_text())
        source["catalog_version"] = "0.1.1"
        source["catalog_status"] = "released"
        self.catalog.write_text(json.dumps(source), encoding="utf-8")
        self.key = Ed25519PrivateKey.generate()
        self.pk = self.key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        self.private = self.key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption())
        self.assets = self.root / "release"
        build(self.catalog, self.assets, self.private)
        self.active = self.root / "active.json"
        installed = json.loads(self.catalog.read_text())
        installed["catalog_version"] = "0.1.0"
        installed["catalog_status"] = "draft"
        self.active.write_text(json.dumps(installed), encoding="utf-8")

    def raws(self):
        return [(self.assets / n).read_bytes() for n in ASSETS]

    def test_signed_release_validates(self):
        self.assertEqual(verify_assets(*self.raws(), self.pk)["catalog_version"], "0.1.1")

    def test_update_creates_previous_and_preserves_content(self):
        before = self.active.read_bytes()
        backup = install_from_assets(self.active, self.assets, self.pk)
        self.assertEqual(backup.read_bytes(), before)
        self.assertEqual(json.loads(self.active.read_text())["catalog_version"], "0.1.1")

    def test_bad_hash_rejected_without_modifying_active(self):
        before = self.active.read_bytes()
        path = self.assets / ASSETS[0]
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            install_from_assets(self.active, self.assets, self.pk)
        self.assertEqual(self.active.read_bytes(), before)

    def test_wrong_key_rejected(self):
        wrong = Ed25519PrivateKey.generate().public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        before = self.active.read_bytes()
        with self.assertRaises(Exception):
            install_from_assets(self.active, self.assets, wrong)
        self.assertEqual(self.active.read_bytes(), before)

    def test_downgrade_rejected(self):
        install_from_assets(self.active, self.assets, self.pk)
        with self.assertRaisesRegex(ValueError, "downgrade"):
            install_from_assets(self.active, self.assets, self.pk)

    def test_release_with_enabled_incident_matching_rejected(self):
        data = json.loads(self.catalog.read_text())
        data["articles"][0]["matching"]["enabled"] = True
        self.catalog.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "matching"):
            build(self.catalog, self.root / "bad", self.private)

    def test_unsigned_manifest_edit_rejected(self):
        path = self.assets / ASSETS[1]
        data = json.loads(path.read_text())
        data["channel"] = "preview"
        path.write_text(json.dumps(data))
        with self.assertRaises(Exception):
            verify_assets(*self.raws(), self.pk)

    def test_channel_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "channel"):
            verify_assets(*self.raws(), self.pk, channel="preview")


if __name__ == "__main__":
    unittest.main(verbosity=2)
