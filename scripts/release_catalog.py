"""Signed GitHub Release catalog packaging. Requires cryptography.

Private key must be PEM Ed25519 from a protected CI secret. Never commit it.
Output release-manifest.json, release-manifest.json.sig and unity-kb-catalog.json.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical(document):
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def build(catalog_path, output, key_pem, channel="stable"):
    catalog_path = Path(catalog_path)
    output = Path(output)
    catalog_bytes = catalog_path.read_bytes()
    catalog = json.loads(catalog_bytes)
    if catalog.get("schema_version") != 1:
        raise ValueError("unsupported catalog schema")
    if catalog.get("catalog_status") != "released":
        raise ValueError("only released catalogs may be packaged")
    if any(a.get("matching", {}).get("enabled") is not False for a in catalog.get("articles", [])):
        raise ValueError("incident matching must remain disabled")
    if channel not in ("stable", "preview"):
        raise ValueError("unsupported release channel")
    key = serialization.load_pem_private_key(key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Ed25519 signing key required")
    manifest = {
        "format_version": 1,
        "catalog_version": catalog["catalog_version"],
        "schema_version": 1,
        "channel": channel,
        "asset": "unity-kb-catalog.json",
        "sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        "size": len(catalog_bytes),
    }
    output.mkdir(parents=True, exist_ok=True)
    manifest_bytes = canonical(manifest)
    (output / "unity-kb-catalog.json").write_bytes(catalog_bytes)
    (output / "release-manifest.json").write_bytes(manifest_bytes)
    (output / "release-manifest.json.sig").write_bytes(key.sign(manifest_bytes))
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="catalog/unity-kb-catalog.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--key", required=True, help="PEM path, from CI secret not repository")
    parser.add_argument("--channel", choices=["stable", "preview"], default="stable")
    args = parser.parse_args()
    build(args.catalog, args.output, Path(args.key).read_bytes(), args.channel)
    print("Signed catalog package written")


if __name__ == "__main__":
    main()
