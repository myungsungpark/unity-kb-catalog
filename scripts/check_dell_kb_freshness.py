"""Read-only Dell KB article metadata freshness checker.

Result codes: 0 = metadata unchanged, 2 = changed/unverified, 3 = unavailable.
This is NOT a content equivalence check, and never edits the catalog.
"""
import argparse
import json
import re
import sys
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "unity-kb-catalog.json"


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self):
        return " ".join(" ".join(self.parts).split())


def normalized_date(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def extract_metadata(page):
    parser = VisibleText()
    parser.feed(page)
    text = parser.text()
    # These labels are displayed in Dell's Article Properties.
    match_id = re.search(r"Article\s+Number\s*:\s*(\d{9})\b", text, re.I)
    match_version = re.search(r"(?:Article\s+)?Version\s*:\s*(\d+)\b", text, re.I)
    match_modified = re.search(
        r"Last\s+Modified\s*:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{4}-\d{2}-\d{2})\b",
        text, re.I
    )
    return {
        "article_number": match_id.group(1) if match_id else None,
        "article_version": int(match_version.group(1)) if match_version else None,
        "last_modified": normalized_date(match_modified.group(1)) if match_modified else None,
    }


def compare_article(article, page):
    metadata = extract_metadata(page)
    expected_id = article["kb_id"]
    if any(value is None for value in metadata.values()):
        return {"kb_id": expected_id, "status": "NEEDS_REVIEW",
                "reason": "Article Properties metadata not fully extractable", "observed": metadata}
    if metadata["article_number"] != expected_id:
        return {"kb_id": expected_id, "status": "NEEDS_REVIEW",
                "reason": "Article number mismatch; possible redirect or wrong page",
                "observed": metadata}
    expected_version = article["article_version"]
    expected_modified = article["last_modified"]
    if metadata["article_version"] != expected_version or metadata["last_modified"] != expected_modified:
        return {"kb_id": expected_id, "status": "CHANGED_METADATA",
                "reason": "Article version or last-modified differs",
                "observed": metadata, "expected": {
                    "article_version": expected_version, "last_modified": expected_modified}}
    return {"kb_id": expected_id, "status": "UNCHANGED_METADATA",
            "reason": "Metadata matched; article content and technical correctness still unverified",
            "observed": metadata}


def fetch_page(url, timeout=15):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "www.dell.com" or not parsed.path.startswith("/support/kbdoc/"):
        raise ValueError("Refusing non-Dell URL")
    request = Request(url, headers={"User-Agent": "UnityKBMetadataCheck/0.1 (+manual verification)"})
    with urlopen(request, timeout=timeout) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "www.dell.com" or not final.path.startswith("/support/kbdoc/"):
            raise ValueError("Refusing redirect outside official Dell KB pages")
        if response.status != 200:
            raise ValueError("Unexpected HTTP status: " + str(response.status))
        return response.read(3_000_000).decode("utf-8", errors="replace")


def run(catalog_path, snapshot_dir=None):
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    results = []
    for article in catalog["articles"]:
        kb_id = article["kb_id"]
        try:
            if snapshot_dir is None:
                page = fetch_page(article["url"])
            else:
                page = (Path(snapshot_dir) / (kb_id + ".html")).read_text(encoding="utf-8")
            result = compare_article(article, page)
        except (OSError, HTTPError, URLError, TimeoutError, ValueError, UnicodeError) as exc:
            result = {"kb_id": kb_id, "status": "UNAVAILABLE",
                      "reason": type(exc).__name__ + ": " + str(exc)}
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--snapshot-dir", type=Path,
                        help="Offline HTML fixtures; omit for live Dell requests")
    args = parser.parse_args()
    try:
        results = run(args.catalog, args.snapshot_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "INVALID_CATALOG", "reason": str(exc)}))
        return 3
    print(json.dumps(results, indent=2, ensure_ascii=False))
    if any(item["status"] == "UNAVAILABLE" for item in results):
        return 3
    if any(item["status"] != "UNCHANGED_METADATA" for item in results):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
