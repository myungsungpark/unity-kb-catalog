"""6-Pre-C: offline-only catalog cache update/rollback simulation.

Not a production downloader. No network, no Release publishing, no signing.
The SHA-256 is integrity-only because the metadata is NOT authenticated.
Only synthetic "stable" candidates are used; draft Catalog is untouched.
"""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


class UpdateRejected(Exception):
    pass


def parse_version(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise UpdateRejected("invalid catalog version")
    return tuple(map(int, value.split(".")))


def strict_json(raw):
    def unique_pairs(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise UpdateRejected("duplicate JSON key: " + key)
            obj[key] = value
        return obj

    try:
        return json.loads(raw, object_pairs_hook=unique_pairs)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise UpdateRejected("invalid or truncated JSON") from exc


def validate_candidate(catalog_bytes, metadata):
    if not isinstance(metadata, dict):
        raise UpdateRejected("invalid update metadata")
    expected_sha = metadata.get("sha256")
    if not isinstance(expected_sha, str) or re.fullmatch(r"[a-f0-9]{64}", expected_sha) is None:
        raise UpdateRejected("invalid SHA-256 field")
    if not isinstance(catalog_bytes, bytes):
        raise UpdateRejected("candidate is not bytes")
    if hashlib.sha256(catalog_bytes).hexdigest() != expected_sha:
        raise UpdateRejected("SHA-256 mismatch")
    try:
        catalog = strict_json(catalog_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise UpdateRejected("candidate is not valid UTF-8") from exc
    if not isinstance(catalog, dict):
        raise UpdateRejected("Catalog is not an object")
    if type(metadata.get("schema_version")) is not int or metadata["schema_version"] != 1:
        raise UpdateRejected("unsupported metadata schema")
    if type(catalog.get("schema_version")) is not int or catalog["schema_version"] != 1:
        raise UpdateRejected("unsupported Catalog schema")
    if metadata.get("catalog_file") != "catalog/unity-kb-catalog.json":
        raise UpdateRejected("unexpected Catalog path")
    if metadata.get("catalog_status") != "stable" or catalog.get("catalog_status") != "stable":
        raise UpdateRejected("only synthetic stable candidates accepted")
    mv = parse_version(metadata.get("catalog_version"))
    cv = parse_version(catalog.get("catalog_version"))
    if mv != cv:
        raise UpdateRejected("manifest/Catalog version mismatch")
    articles = catalog.get("articles")
    if not isinstance(articles, list) or not articles:
        raise UpdateRejected("Catalog articles absent")
    ids = set()
    for article in articles:
        if not isinstance(article, dict) or not isinstance(article.get("kb_id"), str) or re.fullmatch(r"[0-9]{9}", article["kb_id"]) is None:
            raise UpdateRejected("invalid KB entry")
        if article["kb_id"] in ids:
            raise UpdateRejected("duplicate KB ID")
        ids.add(article["kb_id"])
        if not isinstance(article.get("matching"), dict) or article["matching"].get("enabled") is not False:
            raise UpdateRejected("automatic matching must remain disabled")
    return catalog


def envelope(catalog_bytes, metadata):
    candidate = validate_candidate(catalog_bytes, metadata)
    return {"version": metadata["catalog_version"],
            "sha256": metadata["sha256"],
            "catalog": candidate}


def read_envelope(path):
    obj = strict_json(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or not isinstance(obj.get("catalog"), dict):
        raise UpdateRejected("invalid cached envelope")
    raw = json.dumps(obj["catalog"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    # Cache hash is for local corruption detection; metadata authenticity is unverified.
    if not isinstance(obj.get("sha256"), str) or len(obj["sha256"]) != 64:
        raise UpdateRejected("invalid cache digest")
    if obj.get("version") != obj["catalog"].get("catalog_version"):
        raise UpdateRejected("cached version mismatch")
    return obj


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".stage-", dir=str(path.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        # Directory fsync is best-effort, platform-specific and outside this simulation.
    finally:
        if temp.exists():
            temp.unlink()


def update(cache_dir, catalog_bytes, metadata, *, fault=None):
    """Simulate staged update and rollback for controlled failure injection.

    Returns new version on success; errors are raised. No network/keys involved.
    """
    folder = Path(cache_dir)
    active = folder / "active.json"
    previous = folder / "previous.json"
    candidate = envelope(catalog_bytes, metadata)

    current = None
    if active.exists():
        current = read_envelope(active)
        incoming = parse_version(candidate["version"])
        existing = parse_version(current["version"])
        if incoming < existing:
            raise UpdateRejected("catalog downgrade rejected")
        if incoming == existing:
            raise UpdateRejected("same-version replacement rejected")

    if fault == "download_interrupted":
        raise UpdateRejected("download interrupted")
    if fault == "before_commit":
        raise UpdateRejected("injected fault before commit")

    if current is not None:
        _atomic_json(previous, current)
    _atomic_json(active, candidate)

    if fault == "after_commit":
        # Process-controlled rollback; does not simulate uncatchable power failure.
        if current is not None:
            _atomic_json(active, current)
        else:
            active.unlink(missing_ok=True)
        raise UpdateRejected("injected fault after commit: rollback restored")

    return candidate["version"]


def recover(cache_dir):
    """Recover from a corrupted active slot using previous slot, if available."""
    folder = Path(cache_dir)
    active = folder / "active.json"
    previous = folder / "previous.json"
    try:
        return read_envelope(active)
    except (OSError, UpdateRejected, ValueError):
        if not previous.exists():
            raise UpdateRejected("no last-known-good cache")
        backup = read_envelope(previous)
        _atomic_json(active, backup)
        return backup
