"""Synthetic, unit-level matching tests: no real customer logs or live diagnosis."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("matching_simulator", ROOT / "scripts" / "simulate_unity_kb_matching.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ARTICLES = {x["kb_id"]: x for x in json.loads(
    (ROOT / "catalog" / "unity-kb-catalog.json").read_text(encoding="utf-8")
)["articles"]}


def event(**fields):
    return {"event_type": "STORAGE_PROCESSOR_PANIC", **fields}


def run(kb, payload, simulate=True):
    return module.evaluate(copy.deepcopy(ARTICLES[kb]), payload, simulate=simulate)


class TestUnityKBIncidentMatching(unittest.TestCase):
    def test_b01_default_matching_disabled_for_all(self):
        for kb in ARTICLES:
            with self.subTest(kb=kb):
                x = run(kb, event(oe_version="5.3.0.0.5.120"), simulate=False)
                self.assertEqual(x["match_status"], "NOT_EVALUATED")
                self.assertFalse(x["root_cause_confirmed"])
                self.assertFalse(x["simulation_only"])

    def test_b02_host_kernel_panic_excluded_from_all(self):
        for kb in ARTICLES:
            with self.subTest(kb=kb):
                x = run(kb, {"event_type": "HOST_KERNEL_PANIC", "oe_version": "5.3.0.0.5.120"})
                self.assertEqual(x["match_status"], "NOT_MATCHED")

    def test_b03_unknown_event_never_matches(self):
        x = run("000216765", {"oe_version": "5.3.0.0.5.120"})
        self.assertEqual(x["match_status"], "REFERENCE_ONLY")
        self.assertIn("event_type", x["unverified_conditions"])

    def test_b04_missing_oe_never_matches(self):
        x = run("000216765", event(supportassist_enabled=True, zombie_curl=True, no_resources=True))
        self.assertEqual(x["match_status"], "REFERENCE_ONLY")
        self.assertIn("oe_version", x["unverified_conditions"])

    def test_b05_supportassist_strong_synthetic_evidence(self):
        x = run("000216765", event(oe_version="5.3.0.0.5.120", supportassist_enabled=True,
                                   no_resources=True, zombie_curl=True))
        self.assertEqual(x["match_status"], "STRONG_MATCH")
        self.assertFalse(x["root_cause_confirmed"])

    def test_b06_supportassist_partial_evidence_not_strong(self):
        x = run("000216765", event(oe_version="5.3.0.0.5.120", supportassist_enabled=True,
                                   no_resources=True))
        self.assertEqual(x["match_status"], "POSSIBLE_MATCH")

    def test_b07_supportassist_off_not_a_match(self):
        x = run("000216765", event(oe_version="5.3.0.0.5.120", supportassist_enabled=False,
                                   no_resources=True, zombie_curl=True))
        self.assertEqual(x["match_status"], "REFERENCE_ONLY")

    def test_b08_exact_oe_mismatch_no_match(self):
        x = run("000216765", event(oe_version="5.3.1.0.5.008", supportassist_enabled=True,
                                   no_resources=True, zombie_curl=True))
        self.assertEqual(x["match_status"], "REFERENCE_ONLY")

    def test_b09_uptime_strong_evidence(self):
        x = run("000200921", event(oe_version="5.1.0.0.5.394", model="Unity XT 480",
                                   sp_uptime_days=275, udoctor_kb_reference="000200921"))
        self.assertEqual(x["match_status"], "STRONG_MATCH")

    def test_b10_uptime_240_days_not_enough(self):
        x = run("000200921", event(oe_version="5.1.0.0.5.394", model="Unity XT 480",
                                   sp_uptime_days=240, udoctor_kb_reference="000200921"))
        self.assertEqual(x["match_status"], "REFERENCE_ONLY")

    def test_b11_uptime_without_udoctor_possible_only(self):
        x = run("000200921", event(oe_version="5.2.0.0.5.173", model="Unity XT 880",
                                   sp_uptime_days=300))
        self.assertEqual(x["match_status"], "POSSIBLE_MATCH")

    def test_b12_other_models_not_auto_matched(self):
        x = run("000200921", event(oe_version="5.1.0.0.5.394", model="Unity 300",
                                   sp_uptime_days=300, udoctor_kb_reference="000200921"))
        self.assertEqual(x["match_status"], "REFERENCE_ONLY")

    def test_b13_range_outside_not_primary_match(self):
        x = run("000200921", event(oe_version="5.3.0.0.5.120", model="Unity XT 480",
                                   sp_uptime_days=300, udoctor_kb_reference="000200921"))
        self.assertEqual(x["match_status"], "REFERENCE_ONLY")

    def test_b14_mmap_evidence_requires_manual_review(self):
        x = run("000191697", event(oe_version="5.0.2.0.0.000", mmap_count=65530))
        self.assertEqual(x["match_status"], "POSSIBLE_MATCH")
        self.assertIn("manual_oe_review", x["unverified_conditions"])

    def test_b15_mmap_not_exhausted_no_match(self):
        x = run("000191697", event(oe_version="5.0.2.0.0.000", mmap_count=60000))
        self.assertEqual(x["match_status"], "REFERENCE_ONLY")

    def test_b16_mmap_higher_oe_not_automatically_excluded(self):
        x = run("000191697", event(oe_version="5.3.1.0.5.008", mmap_count=65530))
        self.assertEqual(x["match_status"], "POSSIBLE_MATCH")
        self.assertFalse(x["root_cause_confirmed"])

    def test_b17_wrong_oe_format_not_evaluated_as_version_match(self):
        x = run("000200921", event(oe_version="5.1", model="Unity XT 480", sp_uptime_days=280))
        self.assertEqual(x["match_status"], "REFERENCE_ONLY")

    def test_b18_uptime_bool_not_valid_number(self):
        x = run("000200921", event(oe_version="5.1.0.0.5.394", model="Unity XT 480",
                                   sp_uptime_days=True, udoctor_kb_reference="000200921"))
        self.assertEqual(x["match_status"], "REFERENCE_ONLY")

    def test_b19_simulation_does_not_mutate_catalog(self):
        article = copy.deepcopy(ARTICLES["000216765"])
        before = copy.deepcopy(article)
        x = module.evaluate(article, event(oe_version="5.3.0.0.5.120",
                                          supportassist_enabled=True, zombie_curl=True,
                                          no_resources=True), simulate=True)
        self.assertEqual(article, before)
        self.assertFalse(article["matching"]["enabled"])
        self.assertTrue(x["simulation_only"])

    def test_b20_all_match_results_unconfirmed_root_cause(self):
        incidents = {
            "000216765": event(oe_version="5.3.0.0.5.120", supportassist_enabled=True,
                               zombie_curl=True, no_resources=True),
            "000200921": event(oe_version="5.1.0.0.5.394", model="Unity XT 480",
                               sp_uptime_days=280, udoctor_kb_reference="000200921"),
            "000191697": event(oe_version="5.0.2.0.0.000", mmap_count=65530),
        }
        for kb, payload in incidents.items():
            with self.subTest(kb=kb):
                self.assertFalse(run(kb, payload)["root_cause_confirmed"])


if __name__ == "__main__":
    unittest.main()
