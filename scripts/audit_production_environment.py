"""6-B fail-closed audit of GitHub production environment configuration.

This script reads metadata only; GitHub never returns secret VALUES.
Do not use a personal token in logs. Run with GITHUB_TOKEN granted actions/read,
administration/read where available and environments/secrets read permissions.
"""
import argparse
import json
import os
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ENVIRONMENT = "catalog-production"
REQUIRED_SECRETS = {"CATALOG_ED25519_PRIVATE_PEM", "CATALOG_ED25519_PUBLIC_PEM"}


def verify_environment(environment, secret_names, *, require_protected=True):
    errors = []
    if environment.get("name") != ENVIRONMENT:
        errors.append("expected catalog-production environment")
    protection = environment.get("protection_rules", [])
    rules = [r for r in protection if r.get("type") == "required_reviewers"]
    if not rules or not any(r.get("reviewers") for r in rules):
        errors.append("required independent environment reviewers not configured")
    else:
        if any(r.get("prevent_self_review") is False for r in rules):
            errors.append("self-review is not blocked")
    policy = environment.get("deployment_branch_policy") or {}
    if not policy.get("protected_branches") and not policy.get("custom_branch_policies"):
        errors.append("deployment branch restrictions missing")
    if not REQUIRED_SECRETS.issubset(set(secret_names)):
        errors.append("required environment signing secrets missing")
    return errors


def request_json(api, token):
    req = Request("https://api.github.com" + api, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "UnityCatalogSecurityAudit/1",
    })
    with urlopen(req, timeout=20) as response:
        return json.load(response)


def inspect(repo, token):
    env = request_json(f"/repos/{repo}/environments/{ENVIRONMENT}", token)
    secret_response = request_json(f"/repos/{repo}/environments/{ENVIRONMENT}/secrets?per_page=100", token)
    if secret_response.get("total_count", 0) > 100:
        raise RuntimeError("environment secrets listing exceeds first page")
    names = [x["name"] for x in secret_response.get("secrets", [])]
    problems = verify_environment(env, names)
    # Do not claim that an environment reviewer is independent of the triggering
    # publisher from metadata alone. A human must verify the actual reviewer IDs.
    return problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--offline-snapshot", help="optional test-only JSON audit fixture")
    args = parser.parse_args()
    if not args.repo or "/" not in args.repo:
        raise SystemExit("invalid repo argument")
    try:
        if args.offline_snapshot:
            snapshot = json.loads(open(args.offline_snapshot, encoding="utf-8").read())
            problems = verify_environment(snapshot["environment"], snapshot["secrets"])
        else:
            token = os.environ.get("GH_TOKEN", "")
            if not token:
                raise RuntimeError("GH_TOKEN required for production configuration inspection")
            problems = inspect(args.repo, token)
    except (HTTPError, OSError, ValueError, KeyError, RuntimeError) as ex:
        print("6-B SECURITY GATE: UNVERIFIED (cannot read complete configuration)")
        print(type(ex).__name__ + ": " + str(ex))
        return 2
    if problems:
        print("6-B SECURITY GATE: FAIL")
        for item in problems:
            print("FAIL: " + item)
        return 1
    print("6-B SECURITY GATE: CONDITIONAL PASS")
    print("Still requires manual reviewer identity, production key fingerprint and branch protection verification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
