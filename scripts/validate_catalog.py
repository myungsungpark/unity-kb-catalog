
import json
import re
import sys
from pathlib import Path
from datetime import date
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.json"
CATALOG = ROOT / "catalog" / "unity-kb-catalog.json"

errors = []

ALLOWED_STATUSES = {
    "verified",
    "pending",
    "changed",
    "unavailable"
}

ALLOWED_RULE_TYPES = {
    "exact",
    "range",
    "manual_review"
}


def check(condition, message):
    if not condition:
        errors.append(message)


def load_json(path):
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError) as exc:
        errors.append(f"{path.name}: {exc}")
        return None


def parse_date(value):
    if not isinstance(value, str):
        return None
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_version(value, component_count):
    if not isinstance(value, str):
        return None

    parts = value.split(".")

    if len(parts) != component_count:
        return None

    if not all(re.fullmatch(r"[0-9]+", p) for p in parts):
        return None

    return tuple(int(p) for p in parts)


def valid_string_list(value):
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(
            isinstance(item, str) and bool(item.strip())
            for item in value
        )
    )


def valid_dell_url(value, kb_id):
    if not isinstance(value, str):
        return False

    parsed = urlparse(value)

    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.dell.com"
        or parsed.username is not None
        or parsed.password is not None
    ):
        return False

    # URL path must contain the same KB article number.
    pattern = rf"^/support/kbdoc/[a-z]{{2}}-[a-z]{{2}}/{re.escape(kb_id)}(?:/|$)"

    return bool(re.match(pattern, parsed.path))


def validate_oe_rules(article, prefix):
    rules = article.get("oe_rules")

    if not isinstance(rules, list) or not rules:
        errors.append(f"{prefix}: oe_rules must be a nonempty list")
        return

    for index, rule in enumerate(rules, start=1):
        label = f"{prefix} OE rule #{index}"

        if not isinstance(rule, dict):
            errors.append(f"{label}: rule must be an object")
            continue

        rule_type = rule.get("type")

        if not isinstance(rule_type, str) or rule_type not in ALLOWED_RULE_TYPES:
            errors.append(f"{label}: unsupported type {rule_type}")
            continue

        check(
            rule.get("verification")
            == "requires_runtime_evidence",
            f"{label}: invalid verification policy"
        )

        if rule_type == "exact":
            version = parse_version(rule.get("version"), 6)

            check(
                version is not None,
                f"{label}: exact requires a six-part OE version"
            )

        elif rule_type == "range":
            minimum = parse_version(
                rule.get("min_version"), 6
            )
            maximum = parse_version(
                rule.get("max_version"), 6
            )

            check(
                minimum is not None,
                f"{label}: invalid min_version"
            )
            check(
                maximum is not None,
                f"{label}: invalid max_version"
            )

            check(
                isinstance(rule.get("min_inclusive"), bool),
                f"{label}: min_inclusive must be boolean"
            )
            check(
                isinstance(rule.get("max_inclusive"), bool),
                f"{label}: max_inclusive must be boolean"
            )

            if minimum is not None and maximum is not None:
                check(
                    minimum <= maximum,
                    f"{label}: min_version exceeds max_version"
                )
                if minimum == maximum:
                    check(
                        rule.get("min_inclusive") is True
                        and rule.get("max_inclusive") is True,
                        f"{label}: empty OE range"
                    )

        elif rule_type == "manual_review":
            reference = parse_version(
                rule.get("reference_version"), 3
            )

            check(
                reference is not None,
                f"{label}: reference_version must have three parts"
            )

            check(
                isinstance(rule.get("reference_relation"), str)
                and rule.get("reference_relation")
                in {"or_earlier", "or_later", "unspecified"},
                f"{label}: invalid reference_relation"
            )

            check(
                isinstance(rule.get("reason"), str)
                and bool(rule.get("reason", "").strip()),
                f"{label}: manual review reason is required"
            )


def validate_article(article, index, seen_ids):
    prefix = f"Article #{index}"

    if not isinstance(article, dict):
        errors.append(f"{prefix}: article must be an object")
        return

    required_fields = [
        "kb_id",
        "title",
        "url",
        "source",
        "article_version",
        "last_modified",
        "last_checked",
        "verification_status",
        "category",
        "affected_products",
        "affected_oe_versions",
        "oe_rules",
        "conditions",
        "symptoms",
        "matching"
    ]

    for field in required_fields:
        check(
            field in article,
            f"{prefix}: missing {field}"
        )

    kb_id = article.get("kb_id")

    valid_id = (
        isinstance(kb_id, str)
        and bool(re.fullmatch(r"[0-9]{9}", kb_id))
    )

    check(valid_id, f"{prefix}: invalid KB ID")

    if valid_id:
        check(
            kb_id not in seen_ids,
            f"{prefix}: duplicate KB ID {kb_id}"
        )
        seen_ids.add(kb_id)

    check(
        isinstance(article.get("title"), str)
        and bool(article.get("title", "").strip()),
        f"{prefix}: invalid title"
    )

    check(
        article.get("source") == "Dell Official Support",
        f"{prefix}: invalid source"
    )

    check(
        valid_dell_url(
            article.get("url"),
            kb_id if valid_id else "000000000"
        ),
        f"{prefix}: invalid Dell URL or KB ID mismatch"
    )

    version = article.get("article_version")
    check(
        type(version) is int and version > 0,
        f"{prefix}: article_version must be a positive integer"
    )

    modified = parse_date(article.get("last_modified"))
    checked = parse_date(article.get("last_checked"))

    check(
        modified is not None,
        f"{prefix}: invalid last_modified"
    )
    check(
        checked is not None,
        f"{prefix}: invalid last_checked"
    )

    if modified is not None and checked is not None:
        check(
            checked >= modified,
            f"{prefix}: last_checked predates last_modified"
        )

    check(
        isinstance(article.get("verification_status"), str)
        and article.get("verification_status")
        in ALLOWED_STATUSES,
        f"{prefix}: invalid verification_status"
    )

    check(
        isinstance(article.get("category"), str)
        and bool(article.get("category", "").strip()),
        f"{prefix}: invalid category"
    )

    for field in [
        "affected_products",
        "affected_oe_versions",
        "symptoms"
    ]:
        check(
            valid_string_list(article.get(field)),
            f"{prefix}: invalid {field}"
        )

    check(
        isinstance(article.get("conditions"), dict),
        f"{prefix}: conditions must be an object"
    )

    matching = article.get("matching")

    if not isinstance(matching, dict):
        errors.append(f"{prefix}: matching must be an object")
    else:
        check(
            matching.get("enabled") is False,
            f"{prefix}: matching must remain disabled"
        )

        check(
            "match_status" not in matching,
            f"{prefix}: incident match_status belongs in Analyzer"
        )

        for field in [
            "required",
            "supporting_evidence",
            "excluded_event_types"
        ]:
            check(
                valid_string_list(matching.get(field)),
                f"{prefix}: invalid matching.{field}"
            )

    validate_oe_rules(article, prefix)


def main():
    manifest = load_json(MANIFEST)
    catalog = load_json(CATALOG)

    if not isinstance(manifest, dict):
        errors.append("Invalid manifest structure")

    if not isinstance(catalog, dict):
        errors.append("Invalid catalog structure")

    if isinstance(manifest, dict) and isinstance(catalog, dict):

        check(
            type(manifest.get("schema_version")) is int
            and type(catalog.get("schema_version")) is int
            and manifest.get("schema_version") == 1
            and catalog.get("schema_version") == 1,
            "Unsupported schema version"
        )

        check(
            isinstance(manifest.get("catalog_version"), str)
            and isinstance(catalog.get("catalog_version"), str)
            and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", manifest["catalog_version"]) is not None
            and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", catalog["catalog_version"]) is not None,
            "invalid catalog_version"
        )
        check(
            manifest.get("catalog_version") == catalog.get("catalog_version"),
            "Catalog version mismatch"
        )

        check(
            manifest.get("catalog_status") == "draft"
            and catalog.get("catalog_status") == "draft",
            "Expected draft status"
        )

        check(
            manifest.get("catalog_file")
            == "catalog/unity-kb-catalog.json",
            "Unexpected catalog path"
        )

        articles = catalog.get("articles")

        if not isinstance(articles, list):
            errors.append("articles must be a list")
            articles = []

        check(
            len(articles) > 0,
            "No KB articles found"
        )

        seen_ids = set()

        for index, article in enumerate(articles, start=1):
            validate_article(article, index, seen_ids)

        print(f"Checked {len(articles)} KB articles")

    if errors:
        print("\nVALIDATION FAILED")
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("VALIDATION PASSED")
    print(
        "Note: Source content, URL availability, "
        "and actual incident matching are not verified."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
