"""Experimental, deterministic KB incident-matching harness.

No customer data, no log parsing, no automatic matching in production.
The public Catalog's matching.enabled=false always wins unless an explicit
simulate=True flag is passed by a test harness. No root cause is confirmed.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog" / "unity-kb-catalog.json"
SP_PANIC = "STORAGE_PROCESSOR_PANIC"
HOST_PANIC = "HOST_KERNEL_PANIC"
SUPPORTED_KBS = {"000216765", "000200921", "000191697"}


def parse_oe(version, count=6):
    if not isinstance(version, str):
        return None
    parts = version.split(".")
    if len(parts) != count or any(not p.isascii() or not p.isdecimal() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def result(kb_id, status, reasons=(), missing=(), *, simulated=False):
    return {
        "kb_id": kb_id,
        "match_status": status,
        "root_cause_confirmed": False,
        "simulation_only": simulated,
        "reasons": list(reasons),
        "unverified_conditions": list(missing),
    }


def evaluate(article, incident, *, simulate=False):
    """Evaluate *structured synthetic evidence only*, not raw text logs.

    Status is NEVER a confirmed RCA, and any missing required evidence
    cannot produce STRONG_MATCH. Simulated results must not be used in
    Analyzer reports or production decisions.
    """
    kb = article.get("kb_id", "UNKNOWN")
    if not simulate or article.get("matching", {}).get("enabled") is not True and not simulate:
        return result(kb, "NOT_EVALUATED", ["Matching is disabled in the Catalog"])

    # Simulation is explicit; it NEVER changes matching.enabled in source files.
    if not isinstance(incident, dict):
        return result(kb, "REFERENCE_ONLY", ["Incident payload must be an object"], ["incident"], simulated=True)
    if kb not in SUPPORTED_KBS:
        return result(kb, "REFERENCE_ONLY", ["No experimental evaluator for this KB"], simulated=True)

    event = incident.get("event_type")
    if event == HOST_PANIC:
        return result(kb, "NOT_MATCHED", ["Host kernel panic is not a Unity SP panic"], simulated=True)
    if event != SP_PANIC:
        return result(kb, "REFERENCE_ONLY", ["Unity SP panic not independently confirmed"], ["event_type"], simulated=True)

    oe = parse_oe(incident.get("oe_version"))
    if oe is None:
        return result(kb, "REFERENCE_ONLY", ["Unity OE not independently verified"], ["oe_version"], simulated=True)

    rules = article.get("oe_rules", [])
    if not isinstance(rules, list) or not rules or not isinstance(rules[0], dict):
        return result(kb, "REFERENCE_ONLY", ["OE rule missing or unsupported"], simulated=True)
    rule = rules[0]
    kind = rule.get("type")

    if kind == "exact":
        expected = parse_oe(rule.get("version"))
        if expected is None:
            return result(kb, "REFERENCE_ONLY", ["Invalid exact OE rule"], simulated=True)
        if oe != expected:
            return result(kb, "REFERENCE_ONLY", ["OE not in primary reported version"], simulated=True)
    elif kind == "range":
        low = parse_oe(rule.get("min_version"))
        high = parse_oe(rule.get("max_version"))
        if low is None or high is None or low > high:
            return result(kb, "REFERENCE_ONLY", ["Invalid range OE rule"], simulated=True)
        if (oe < low or oe > high or
            (oe == low and rule.get("min_inclusive") is not True) or
            (oe == high and rule.get("max_inclusive") is not True)):
            return result(kb, "REFERENCE_ONLY", ["OE outside primary reported version range"], simulated=True)
    elif kind == "manual_review":
        # An indicative version is not a hard exclusion or automatic inclusion.
        return _evaluate_mmap(kb, incident, simulated=True)
    else:
        return result(kb, "REFERENCE_ONLY", ["Unsupported OE rule type"], simulated=True)

    if kb == "000216765":
        if incident.get("supportassist_enabled") is not True:
            return result(kb, "REFERENCE_ONLY", ["SupportAssist enabled not verified"],
                          ["supportassist_enabled"], simulated=True)
        missing = [name for name in ("no_resources", "zombie_curl")
                   if incident.get(name) is not True]
        if missing:
            return result(kb, "POSSIBLE_MATCH", ["SP panic, exact OE and SupportAssist confirmed"],
                          missing, simulated=True)
        return result(kb, "STRONG_MATCH",
                      ["SP panic, exact OE, SupportAssist and both indicative errors supplied"],
                      simulated=True)

    if kb == "000200921":
        models = article.get("primary_affected_models", [])
        if incident.get("model") not in models:
            return result(kb, "REFERENCE_ONLY", ["Model not independently confirmed in primary affected models"],
                          ["model"], simulated=True)
        uptime = incident.get("sp_uptime_days")
        if type(uptime) not in (float, int) or uptime <= 240:
            return result(kb, "REFERENCE_ONLY", ["SP uptime over 240 days not verified"],
                          ["sp_uptime_days"], simulated=True)
        if incident.get("udoctor_kb_reference") == kb:
            return result(kb, "STRONG_MATCH",
                          ["SP panic, primary model/OE, uptime > 240 days and UDoctor KB reference"],
                          simulated=True)
        return result(kb, "POSSIBLE_MATCH",
                      ["SP panic, primary model/OE and uptime > 240 days"],
                      ["udoctor_kb_reference"], simulated=True)

    return result(kb, "REFERENCE_ONLY", ["No evaluator for KB"], simulated=True)


def _evaluate_mmap(kb, incident, *, simulated):
    # The Catalog uses manual_review: always requires an actual incident RCA.
    count = incident.get("mmap_count")
    if type(count) is not int or count < 65530:
        return result(kb, "REFERENCE_ONLY", ["MMAP exhaustion not verified"],
                      ["mmap_count"], simulated=simulated)
    return result(kb, "POSSIBLE_MATCH", ["SP panic and MMAP mapping threshold evidenced; manual OE review needed"],
                  ["manual_oe_review"], simulated=simulated)


def main():
    parser = argparse.ArgumentParser(description="Simulation-only evaluator of synthetic structured incident evidence")
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--simulate", action="store_true",
                        help="Explicitly enable simulation; never enables Catalog matching")
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    incident = json.loads(args.fixture.read_text(encoding="utf-8"))
    evaluations = [evaluate(article, incident, simulate=args.simulate) for article in catalog["articles"]]
    print(json.dumps(evaluations, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
