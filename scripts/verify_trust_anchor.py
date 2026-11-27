"""6-B secure key fingerprint validation, without displaying private material.

The approved fingerprint is the SHA-256 hex digest of *raw 32-byte* Ed25519
public key bytes, not PEM text. An independent administrator must compare it
with an out-of-band trust record and the pinned key shipped with Analyzer.
"""
import argparse
import hashlib
import hmac
import re
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def raw_ed25519_key(public_pem):
    key = serialization.load_pem_public_key(public_pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Ed25519 public key required")
    return key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def require_pinned_fingerprint(public_pem, expected_sha256):
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("approved public-key SHA-256 fingerprint required")
    raw = raw_ed25519_key(public_pem)
    actual = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual, expected_sha256):
        raise ValueError("public signing key differs from approved trust anchor")
    return actual


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--public-key", type=Path, required=True)
    p.add_argument("--expected-sha256", required=True)
    args = p.parse_args()
    require_pinned_fingerprint(args.public_key.read_bytes(), args.expected_sha256)
    print("APPROVED TRUST ANCHOR MATCH: PASS")
    # Do not print PEM, private-key material or unapproved candidate fingerprints.


if __name__ == "__main__":
    main()
