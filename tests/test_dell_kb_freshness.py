"""Offline tests for the read-only Dell KB metadata freshness checker.

No network requests. Every test builds temporary HTML fixtures.
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_dell_kb_freshness.py"
CATALOG = json.loads((ROOT / "catalog" / "unity-kb-catalog.json").read_text(encoding="utf-8"))


def fixture(article, version=None, last_modified=None, kb_id=None):
    return (
        "<html><head><title>Official KB sample</title></head><body>"
        "<h3>Article Properties</h3>"
        f"<p>Article Number: {kb_id or article['kb_id']}</p>"
        f"<p>Article Version: {version if version is not None else article['article_version']}</p>"
        f"<p>Last Modified: {last_modified if last_modified is not None else article['last_modified']}</p>"
        "</body></html>"
    )


def run(snapshot_edit=None, missing=None):
    with tempfile.TemporaryDirectory(prefix="dell-kb-freshness-") as temp:
        directory = Path(temp)
        snapshots = directory / "snapshots"
        snapshots.mkdir()
        catalog_file = directory / "catalog.json"
        catalog_file.write_text(json.dumps(CATALOG), encoding="utf-8")
        for article in CATALOG["articles"]:
            kb = article["kb_id"]
            if kb == missing:
                continue
            page = fixture(article)
            if snapshot_edit and kb in snapshot_edit:
                page = snapshot_edit[kb](article)
            (snapshots / (kb + ".html")).write_text(page, encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--catalog", str(catalog_file),
             "--snapshot-dir", str(snapshots)],
            capture_output=True, text=True, timeout=30, check=False
        )
        return completed.returncode, json.loads(completed.stdout), completed.stderr


class TestDellKBMetadataFreshness(unittest.TestCase):
    def test_prea01_three_articles_unchanged(self):
        code, results, err = run()
        self.assertEqual(code, 0, (results, err))
        self.assertEqual(len(results), 3)
        self.assertTrue(all(x["status"] == "UNCHANGED_METADATA" for x in results))

    def test_prea02_article_version_change_detected(self):
        kb = CATALOG["articles"][0]["kb_id"]
        code, results, _ = run({kb: lambda x: fixture(x, version=x["article_version"] + 1)})
        self.assertEqual(code, 2)
        self.assertEqual(results[0]["status"], "CHANGED_METADATA")

    def test_prea03_last_modified_change_detected(self):
        kb = CATALOG["articles"][0]["kb_id"]
        code, results, _ = run({kb: lambda x: fixture(x, last_modified="2026-11-29")})
        self.assertEqual(code, 2)
        self.assertEqual(results[0]["status"], "CHANGED_METADATA")

    def test_prea04_wrong_article_number_requires_review(self):
        kb = CATALOG["articles"][0]["kb_id"]
        code, results, _ = run({kb: lambda x: fixture(x, kb_id="000000001")})
        self.assertEqual(code, 2)
        self.assertEqual(results[0]["status"], "NEEDS_REVIEW")

    def test_prea05_missing_properties_requires_review(self):
        kb = CATALOG["articles"][0]["kb_id"]
        code, results, _ = run({kb: lambda x: "<html><body>No metadata</body></html>"})
        self.assertEqual(code, 2)
        self.assertEqual(results[0]["status"], "NEEDS_REVIEW")

    def test_prea06_missing_page_unavailable_not_pass(self):
        kb = CATALOG["articles"][1]["kb_id"]
        code, results, _ = run(missing=kb)
        self.assertEqual(code, 3)
        self.assertEqual(results[1]["status"], "UNAVAILABLE")

    def test_prea07_script_metadata_ignored(self):
        kb = CATALOG["articles"][0]["kb_id"]
        code, results, _ = run({kb: lambda x: "<script>Article Number: " + kb + " Article Version: " +
                                str(x["article_version"]) + " Last Modified: " + x["last_modified"] +
                                "</script><body>Missing metadata</body>"})
        self.assertEqual(code, 2)
        self.assertEqual(results[0]["status"], "NEEDS_REVIEW")

    def test_prea08_human_review_required_for_unchanged_metadata(self):
        code, results, _ = run()
        self.assertEqual(code, 0)
        self.assertTrue(all("content and technical correctness still unverified" in x["reason"] for x in results))


if __name__ == "__main__":
    unittest.main()
