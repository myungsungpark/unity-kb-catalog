"""Fail-closed signed Catalog updater for Analyzer integration.

No automatic activation until Analyzer calls install_from_assets with a
trusted Ed25519 public key shipped independently in the application.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.request import Request, urlopen
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ASSETS = ("unity-kb-catalog.json", "release-manifest.json", "release-manifest.json.sig")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def version(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError("invalid catalog version")
    return tuple(map(int, value.split(".")))


def load_public_key(raw):
    if len(raw) != 32:
        raise ValueError("Ed25519 public key must be exactly 32 bytes")
    return Ed25519PublicKey.from_public_bytes(raw)


def verify_assets(catalog_bytes, manifest_bytes, signature_bytes, public_key, *,
                  installed_version=None, analyzer_version=None, channel="stable", allow_rollback=False):
    if len(catalog_bytes) > 16 * 1024 * 1024 or len(manifest_bytes) > 64 * 1024:
        raise ValueError("oversized release asset")
    load_public_key(public_key).verify(signature_bytes, manifest_bytes)
    manifest = json.loads(manifest_bytes)
    catalog = json.loads(catalog_bytes)
    if manifest.get("format_version") != 1 or manifest.get("schema_version") != 1:
        raise ValueError("unsupported release format")
    minimum = manifest.get("min_analyzer_version")
    def analyzer_parts(s):
        m = re.fullmatch(r"([0-9]+)\\.([0-9]+)-RC([0-9]+)", s or "")
        if not m:
            raise ValueError("invalid Analyzer version")
        return tuple(map(int, m.groups()))
    if not isinstance(minimum, str):
        raise ValueError("missing minimum Analyzer version")
    analyzer_parts(minimum)
    if analyzer_version is None:
        raise ValueError("Analyzer version required")
    if analyzer_parts(analyzer_version) < analyzer_parts(minimum):
        raise ValueError("Analyzer version incompatible")
    if manifest.get("channel") != channel or manifest.get("asset") != ASSETS[0]:
        raise ValueError("release channel or asset mismatch")
    if manifest.get("sha256") != hashlib.sha256(catalog_bytes).hexdigest():
        raise ValueError("checksum mismatch")
    if manifest.get("size") != len(catalog_bytes):
        raise ValueError("size mismatch")
    if catalog.get("schema_version") != 1 or catalog.get("catalog_status") != "released":
        raise ValueError("catalog is not released")
    if manifest.get("catalog_version") != catalog.get("catalog_version"):
        raise ValueError("catalog version mismatch")
    if not isinstance(catalog.get("articles"), list) or not catalog["articles"]:
        raise ValueError("catalog articles missing")
    if any(not isinstance(a, dict) or a.get("matching", {}).get("enabled") is not False
           for a in catalog["articles"]):
        raise ValueError("incident matching cannot be enabled")
    candidate = version(catalog["catalog_version"])
    if installed_version is not None:
        current = version(installed_version)
        if candidate <= current and not allow_rollback:
            raise ValueError("downgrade or same version rejected")
    return catalog


def install_from_assets(active_path, asset_dir, public_key, *, channel="stable",
                        allow_rollback=False, analyzer_version=None):
    """Atomic replacement on same filesystem; retain last-known-good backup.

    Caller must serialize updater access, close Analyzer file handles, and
    handle power-loss journal recovery before using in production.
    """
    active = Path(active_path)
    directory = Path(asset_dir)
    raw = [(directory / name).read_bytes() for name in ASSETS]
    old_bytes = active.read_bytes() if active.exists() else None
    old_version = json.loads(old_bytes)["catalog_version"] if old_bytes else None
    verify_assets(*raw, public_key, installed_version=old_version,
                  channel=channel, allow_rollback=allow_rollback,
                  analyzer_version=analyzer_version)
    active.parent.mkdir(parents=True, exist_ok=True)
    backup = active.with_name(active.name + ".previous")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=active.parent, prefix=".catalog-",
                                         delete=False) as f:
            tmp_path = Path(f.name)
            f.write(raw[0])
            f.flush()
            os.fsync(f.fileno())
        if old_bytes is not None:
            with tempfile.NamedTemporaryFile(dir=active.parent, prefix=".previous-",
                                             delete=False) as f:
                backup_tmp = Path(f.name)
                f.write(old_bytes)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.replace(backup_tmp, backup)
            finally:
                backup_tmp.unlink(missing_ok=True)
        os.replace(tmp_path, active)
        tmp_path = None
        if hashlib.sha256(active.read_bytes()).digest() != hashlib.sha256(raw[0]).digest():
            raise ValueError("post-activation hash mismatch")
        return backup if old_bytes is not None else None
    except Exception:
        if old_bytes is not None and backup.exists():
            os.replace(backup, active)
        raise
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def download_release_assets(repo, tag, destination):
    """Download exactly 3 assets from pinned GitHub repo and explicit tag.

    URL and tag come from locally trusted configuration; not catalog JSON.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("invalid repository")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", tag):
        raise ValueError("invalid tag")
    url = "https://api.github.com/repos/" + repo + "/releases/tags/" + tag
    def get(url, limit):
        request = Request(url, headers={"User-Agent": "UnityCatalogUpdater/1", "Accept": "application/vnd.github+json"})
        with urlopen(request, timeout=20) as response:
            data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("asset exceeds size limit")
        return data
    release = json.loads(get(url, 1024 * 1024))
    if release.get("draft") or release.get("prerelease") or release.get("tag_name") != tag:
        raise ValueError("not an approved release tag")
    found = {a["name"]: a for a in release.get("assets", []) if isinstance(a, dict) and "name" in a}
    if any(n not in found for n in ASSETS):
        raise ValueError("missing signed release assets")
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        uri = found[name]["browser_download_url"]
        if not uri.startswith("https://github.com/" + repo + "/releases/download/" + tag + "/"):
            raise ValueError("untrusted asset download URL")
        limit = 16 * 1024 * 1024 if name == ASSETS[0] else 64 * 1024
        (dest / name).write_bytes(get(uri, limit))
    return dest
