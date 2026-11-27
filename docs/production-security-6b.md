# 6-B — Production Environment and signing-key security verification

**Status: UNVERIFIED for the live production environment.** This repo's
GitHub connection does not expose environment configuration, protection
rules, secret metadata or branch rulesets. No production private key was
created, read, uploaded or rotated during this task.

## Required controls (fail closed)
1. Protect `main`: disallow force pushes and direct updates; require
   independent PR reviews and required successful checks.
2. Create `catalog-production` in **Settings → Environments**.
   Require deployment from **protected branches**, ideally explicitly
   restrict to `main`; require at least one reviewer who is not the
   release initiator, and enable **Prevent self-review** where supported.
   GitHub plan, repository visibility and organization policy may affect
   available environment protection rules. If required reviewers cannot
   be enforced, do not use this publishing workflow for Stable releases.
3. Configure **environment-scoped** secrets:
   `CATALOG_ED25519_PRIVATE_PEM` (Ed25519 PKCS#8 PEM private key) and
   `CATALOG_ED25519_PUBLIC_PEM` (corresponding SPKI PEM public key).
   Secret *metadata* is not sufficient to prove values are valid or match.
   Do not send private keys or secret values to the assistant.
4. Independently verify the production public-key fingerprint through a
   trusted out-of-band channel and embed its raw 32-byte Ed25519 key in
   an approved Windows Analyzer build. A GitHub Release asset MUST NOT
   be used as the Analyzer's root of trust.
5. Limit `GITHUB_TOKEN` scope to read except for the approved publisher.
   Review all actors who can edit Workflow files, secrets, environments
   and branch protection. Use environment approval and protected branch
   together; one does not replace the other.
6. Establish documented key creation, custody, rotation, backup and
   emergency revocation procedures. Secret exposure requires key
   retirement, client trust update, security incident review and
   publication suspension.
7. Enforce immutable unique tags `catalog-vX.Y.Z`. Archive SHA-256 of
   the catalog and manifest, the reviewed source SHA, approval record,
   release ID and CI run IDs. Never overwrite an existing release/tag.

## Metadata verification
With an appropriately scoped, temporary administrative **read-only**
GitHub token, run in a secure admin terminal:

```bash
GH_TOKEN=... python3 scripts/audit_production_environment.py --repo myungsungpark/unity-kb-catalog
```

The script inspects environment metadata and required secret names.
It explicitly prints *CONDITIONAL PASS*, not a production security
certification, even if the metadata matches. A missing permission
causes *UNVERIFIED* (exit 2), never PASS. Failed controls exit 1.

**Manual evidence still required:** actual required reviewer identities,
self-review prevention, deployment branch policy exactness, `main`
branch protection, scoped deploy permissions, signer/private-key validity,
out-of-band public key fingerprint, key ownership and rotation plan.

## Self-review limitation
Environment metadata can differ by GitHub API version. Inspect the actual
GitHub UI and enforce self-review prevention there. The offline fixture
tests model expected rules but cannot certify live policy.

## CI limitation
`6-b-security-audit.yml` tests synthetic metadata in isolated runners.
It does not fetch or authenticate live production environment
configuration and does not sign or publish a Stable Release.

## Stop/go decision
Do not merge PR #8 or #9 for publication, and never execute
`6-A Publish Signed Catalog Release` with `PUBLISH` until:
- branch/environment/secret policy reviewed and documented;
- signed trust key integrated and verified on Windows x64 Analyzer;
- rollback/downgrade, power-loss, concurrent update, and key-rotation
  verification complete;
- three independent signed-release verification passes are evidenced.

This is intentionally separate from CI success and from code build status.
