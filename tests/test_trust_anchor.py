"""6-B trust-anchor negative tests, no production signing materials."""
import hashlib
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from scripts.verify_trust_anchor import require_pinned_fingerprint


class TestApprovedTrustAnchor(unittest.TestCase):
    def setUp(self):
        private = Ed25519PrivateKey.generate()
        self.pem = private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        raw = private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        self.approved = hashlib.sha256(raw).hexdigest()

    def test_approved_public_key_passes(self):
        self.assertEqual(require_pinned_fingerprint(self.pem, self.approved), self.approved)

    def test_unapproved_public_key_fails(self):
        other = Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        with self.assertRaisesRegex(ValueError, "differs"):
            require_pinned_fingerprint(other, self.approved)

    def test_missing_fingerprint_fails(self):
        with self.assertRaisesRegex(ValueError, "required"):
            require_pinned_fingerprint(self.pem, "")

    def test_noncanonical_fingerprint_fails(self):
        with self.assertRaisesRegex(ValueError, "required"):
            require_pinned_fingerprint(self.pem, self.approved.upper())

    def test_wrong_key_algorithm_fails(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        rsa_pem = private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        with self.assertRaisesRegex(ValueError, "Ed25519"):
            require_pinned_fingerprint(rsa_pem, self.approved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
