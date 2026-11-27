"""Security policy regression tests; do not contact GitHub or inspect key values."""
import copy
import unittest
from scripts.audit_production_environment import verify_environment

def baseline():
    return {
        "name": "catalog-production",
        "protection_rules": [{"type": "required_reviewers",
                              "reviewers": [{"type": "User", "reviewer": {"login": "reviewer"}}],
                              "prevent_self_review": True}],
        "deployment_branch_policy": {"protected_branches": True, "custom_branch_policies": False}
    }

SECRETS = ["CATALOG_ED25519_PRIVATE_PEM", "CATALOG_ED25519_PUBLIC_PEM"]


class TestProductionSecurityAudit(unittest.TestCase):
    def test_complete_policy_conditionally_passes(self):
        self.assertEqual(verify_environment(baseline(), SECRETS), [])

    def test_missing_environment_fails(self):
        e = baseline()
        e["name"] = "preview"
        self.assertTrue(verify_environment(e, SECRETS))

    def test_missing_reviewers_fails(self):
        e = baseline()
        e["protection_rules"] = []
        self.assertTrue(verify_environment(e, SECRETS))

    def test_empty_reviewers_fails(self):
        e = baseline()
        e["protection_rules"][0]["reviewers"] = []
        self.assertTrue(verify_environment(e, SECRETS))

    def test_self_review_explicitly_allowed_fails(self):
        e = baseline()
        e["protection_rules"][0]["prevent_self_review"] = False
        self.assertTrue(verify_environment(e, SECRETS))

    def test_missing_branch_policy_fails(self):
        e = baseline()
        e["deployment_branch_policy"] = {"protected_branches": False, "custom_branch_policies": False}
        self.assertTrue(verify_environment(e, SECRETS))

    def test_missing_private_key_fails(self):
        self.assertTrue(verify_environment(baseline(), [SECRETS[1]]))

    def test_missing_public_key_fails(self):
        self.assertTrue(verify_environment(baseline(), [SECRETS[0]]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
