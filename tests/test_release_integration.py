"""6-Pre-C: GitHub Release asset download + signature + rollback integration tests.
Only for isolated CI, not production Analyzer updater.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(os.environ["RELEASE_ASSETS"])
PUBKEY = Path(os.environ["TEST_PUBLIC_KEY"])


def signature_ok(payload, signature):
    return subprocess.run(
        ["openssl", "dgst", "-sha256", "-verify", str(PUBKEY),
         "-signature", str(signature), str(payload)],
        capture_output=True, text=True, check=False,
    ).returncode == 0


def apply_update(current, candidate, manifest, signature, fail_after_activation=False):
    data = candidate.read_bytes()
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(data).hexdigest() != metadata["sha256"]:
        raise ValueError("checksum mismatch")
    if not signature_ok(candidate, signature):
        raise ValueError("signature invalid")
    new = json.loads(data)
    old = json.loads(current.read_text(encoding="utf-8"))
    if new.get("schema_version") != 1:
        raise ValueError("unsupported schema")
    if new.get("catalog_status") != "draft":
        raise ValueError("invalid status")
    if any(a.get("matching", {}).get("enabled") is not False for a in new["articles"]):
        raise ValueError("matching safety policy")
    if new["catalog_version"] != metadata["catalog_version"]:
        raise ValueError("manifest version mismatch")
    def version(v):
        p = v.split(".")
        if len(p) != 3 or not all(x.isdecimal() for x in p):
            raise ValueError("bad version")
        return tuple(int(x) for x in p)
    if version(new["catalog_version"]) <= version(old["catalog_version"]):
        raise ValueError("not a newer version")
    backup = current.with_suffix(".previous")
    staging = current.with_suffix(".staged")
    shutil.copy2(current, backup)
    try:
        staging.write_bytes(data)
        os.replace(staging, current)
        if fail_after_activation:
            raise RuntimeError("injected activation failure")
        if json.loads(current.read_text())["catalog_version"] != metadata["catalog_version"]:
            raise RuntimeError("post-activation verification failure")
    except Exception:
        os.replace(backup, current)
        raise
    finally:
        staging.unlink(missing_ok=True)
    return backup


class ReleaseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.active = self.work / "active.json"
        shutil.copy2(ROOT / "catalog" / "unity-kb-catalog.json", self.active)
        self.candidate = ASSETS / "unity-kb-catalog.json"
        self.manifest = ASSETS / "release-manifest.json"
        self.signature = ASSETS / "unity-kb-catalog.json.sig"

    def test_01_real_release_downloaded_and_signed(self):
        self.assertTrue(self.candidate.is_file())
        self.assertTrue(signature_ok(self.candidate, self.signature))
        self.assertEqual(json.loads(self.candidate.read_text())["catalog_version"], "0.1.1")

    def test_02_update_then_manual_rollback(self):
        before = self.active.read_bytes()
        backup = apply_update(self.active, self.candidate, self.manifest, self.signature)
        self.assertEqual(json.loads(self.active.read_text())["catalog_version"], "0.1.1")
        os.replace(backup, self.active)
        self.assertEqual(self.active.read_bytes(), before)

    def test_03_hash_tamper_rejected_preserves_old(self):
        bad = self.work / "modified.json"
        bad.write_bytes(self.candidate.read_bytes() + b" ")
        before = self.active.read_bytes()
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            apply_update(self.active, bad, self.manifest, self.signature)
        self.assertEqual(self.active.read_bytes(), before)

    def test_04_bad_signature_rejected_preserves_old(self):
        wrong = self.work / "wrong.sig"
        wrong.write_bytes(b"invalid signature")
        before = self.active.read_bytes()
        with self.assertRaisesRegex(ValueError, "signature invalid"):
            apply_update(self.active, self.candidate, self.manifest, wrong)
        self.assertEqual(self.active.read_bytes(), before)

    def test_05_activation_failure_auto_rolls_back(self):
        before = self.active.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "injected activation"):
            apply_update(self.active, self.candidate, self.manifest, self.signature, True)
        self.assertEqual(self.active.read_bytes(), before)

    def test_06_downgrade_rejected(self):
        shutil.copy2(self.candidate, self.active)
        before = self.active.read_bytes()
        with self.assertRaisesRegex(ValueError, "not a newer"):
            apply_update(self.active, self.candidate, self.manifest, self.signature)
        self.assertEqual(self.active.read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
