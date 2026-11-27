"""Verify exact downloaded GitHub Release assets using a pinned Ed25519 public key."""
import argparse
import hashlib
import json
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from scripts.catalog_updater import ASSETS, verify_assets


def verify_directory(asset_dir, public_pem, expected_version, expected_tag, analyzer_version, channel):
    asset_dir = Path(asset_dir)
    if expected_tag != "catalog-v" + expected_version:
        raise ValueError("tag and expected version mismatch")
    public_key = serialization.load_pem_public_key(Path(public_pem).read_bytes())
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError("Ed25519 public key required")
    from cryptography.hazmat.primitives import serialization as s
    raw_key = public_key.public_bytes(s.Encoding.Raw, s.PublicFormat.Raw)
    data = [(asset_dir / name).read_bytes() for name in ASSETS]
    parsed = verify_assets(*data, raw_key, analyzer_version=analyzer_version, channel=channel)
    if parsed["catalog_version"] != expected_version:
        raise ValueError("unexpected signed catalog version")
    if json.loads(data[1])["release_tag"] != expected_tag:
        raise ValueError("unexpected signed release tag")
    return hashlib.sha256(data[0]).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--assets", required=True)
    p.add_argument("--public-key", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--analyzer-version", required=True)
    p.add_argument("--channel", default="stable")
    a = p.parse_args()
    digest = verify_directory(a.assets, a.public_key, a.version, a.tag, a.analyzer_version, a.channel)
    print("SIGNED RELEASE VERIFIED sha256=" + digest)


if __name__ == "__main__":
    main()
