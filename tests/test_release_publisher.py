"""6-A release candidate preparation and signed-tag binding regression tests."""
import json
from pathlib import Path
import tempfile
import unittest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from scripts.prepare_release import ROOT, prepare
from scripts.release_catalog import build
from scripts.catalog_updater import verify_assets

class ReleasePublisherTests(unittest.TestCase):
    def test_prepare_requires_version_matching_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "version and draft"):
                prepare(ROOT, tmp, "9.9.9")

    def test_validated_draft_is_transformed_only_in_output(self):
        source = ROOT / "catalog/unity-kb-catalog.json"
        before = source.read_bytes()
        version = json.loads(before)["catalog_version"]
        with tempfile.TemporaryDirectory() as tmp:
            candidate = prepare(ROOT, tmp, version)
            self.assertEqual(json.loads(candidate.read_text())["catalog_status"], "released")
            self.assertEqual(source.read_bytes(), before)

    def test_publisher_signs_release_tag_and_verifier_accepts_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            version = json.loads((ROOT / "manifest.json").read_text())["catalog_version"]
            candidate = prepare(ROOT, root / "prepared", version)
            key = Ed25519PrivateKey.generate()
            private = key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
            public = key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
            manifest = build(candidate, root / "assets", private)
            self.assertEqual(manifest["release_tag"], "catalog-v" + version)
            assets = root / "assets"
            verified = verify_assets((assets / "unity-kb-catalog.json").read_bytes(),
                (assets / "release-manifest.json").read_bytes(),
                (assets / "release-manifest.json.sig").read_bytes(),
                public, analyzer_version="1.0-RC15")
            self.assertEqual(verified["catalog_version"], version)

    def test_signed_tag_and_version_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            version = json.loads((ROOT / "manifest.json").read_text())["catalog_version"]
            candidate = prepare(ROOT, root / "prepared", version)
            key = Ed25519PrivateKey.generate()
            private = key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
            public = key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
            build(candidate, root / "assets", private)
            p = root / "assets"
            doc = json.loads((p / "release-manifest.json").read_text())
            doc["release_tag"] = "catalog-v9.9.9"
            bad_manifest = (json.dumps(doc) + "\n").encode()
            bad_signature = key.sign(bad_manifest)
            with self.assertRaisesRegex(ValueError, "tag mismatch"):
                verify_assets((p / "unity-kb-catalog.json").read_bytes(),bad_manifest,bad_signature,
                              public,analyzer_version="1.0-RC15")

if __name__ == "__main__":
    unittest.main(verbosity=2)
