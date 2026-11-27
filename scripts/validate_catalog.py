
import json
import sys
from pathlib import Path
from datetime import date
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "unity-kb-catalog.json"
MANIFEST = ROOT / "manifest.json"

errors = []


def check(condition, message):
    if not condition:
        errors.append(message)


def load_json(path):
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        errors.append(f"{path.name}: {exc}")
        return None


def valid_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def valid_dell_url(value):
    if not isinstance(value, str):
        return False

    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "www.dell.com"
        and parsed.path.startswith("/support/kbdoc/")
    )


manifest = load_json(MANIFEST)
catalog = load_json(CATALOG)

if not isinstance(manifest, dict):
    errors.append("Invalid manifest structure")

if not isinstance(catalog, dict):
    errors.append("Invalid catalog structure")

if isinstance(manifest, dict) and isinstance(catalog, dict):

    check(
        manifest.get("catalog_version")
        == catalog.get("catalog_version"),
        "Catalog version mismatch"
    )

    check(
        manifest.get("catalog_status") == "draft"
        and catalog.get("catalog_status") == "draft",
        "Expected draft status"
    )

    check(
        manifest.get("schema_version") == 1
        and catalog.get("schema_version") == 1,
        "Unsupported schema version"
    )

    check(
        manifest.get("catalog_file")
        == "catalog/unity-kb-catalog.json",
        "Unexpected catalog file path"
    )

    articles = catalog.get("articles")

    if not isinstance(articles, list):
        errors.append("articles must be a list")
        articles = []

    check(len(articles) > 0, "No KB articles found")

    seen_ids = set()

    required_fields = [
        "kb_id",
        "title",
        "url",
        "source",
        "category",
        "verification_status",
        "affected_products",
        "affected_oe_versions",
        "conditions",
        "symptoms",
        "matching"
    ]

    for index, article in enumerate(articles, start=1):
        prefix = f"Article #{index}"

        if not isinstance(article, dict):
            errors.append(f"{prefix}: invalid object")
            continue

        for field in required_fields:
            check(
                field in article,
                f"{prefix}: missing {field}"
            )

        kb_id = article.get("kb_id")

        check(
            isinstance(kb_id, str)
            and len(kb_id) == 9
            and kb_id.isdigit(),
            f"{prefix}: invalid KB ID"
        )

        if kb_id in seen_ids:
            errors.append(f"Duplicate KB ID: {kb_id}")

        seen_ids.add(kb_id)

        check(
            isinstance(article.get("title"), str)
            and bool(article.get("title").strip()),
            f"{prefix}: invalid title"
        )

        check(
            valid_dell_url(article.get("url")),
            f"{prefix}: invalid Dell URL"
        )

        for field in ["last_modified", "last_checked"]:
            if field in article:
                check(
                    valid_date(article[field]),
                    f"{prefix}: invalid {field}"
                )

        check(
            article.get("verification_status")
            in ["verified", "pending", "changed", "unavailable"],
            f"{prefix}: invalid verification status"
        )

        for field in [
            "affected_products",
            "affected_oe_versions",
            "symptoms"
        ]:
            value = article.get(field)
            check(
                isinstance(value, list)
                and len(value) > 0
                and all(isinstance(x, str) and x.strip() for x in value),
                f"{prefix}: invalid {field}"
            )

        check(
            isinstance(article.get("conditions"), dict),
            f"{prefix}: conditions must be an object"
        )

        matching = article.get("matching")
        check(
            isinstance(matching, dict)
            and matching.get("enabled") is False,
            f"{prefix}: matching must be disabled"
        )

print(f"Checked {len(catalog.get('articles', [])) if isinstance(catalog, dict) and isinstance(catalog.get('articles'), list) else 0} KB articles")

if errors:
    print("\nVALIDATION FAILED")
    for error in errors:
        print(f"ERROR: {error}")
    sys.exit(1)

print("VALIDATION PASSED")
print("Note: Dell article content and URL availability are not checked.")
