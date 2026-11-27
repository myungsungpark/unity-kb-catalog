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

## 6-B-1 observed GitHub repository state (2026-11-27)

API `GET /repos/myungsungpark/unity-kb-catalog/branches/main` reported
`protected: false` at commit
`53619900e79d18e8fe5c7de80c45b5745678667d`. Rulesets collection
reported `[]`. Protected branch details returned HTTP 403 to the connector.
Environment and secret metadata cannot be queried with this integration.
Therefore the operational 6-B-1 approval decision is **FAIL / HOLD**.

### Required administrator action and evidence

1. Configure `main` protection under Settings → Branches or Rulesets,
   with mandatory review(s), required CI status checks, no force push/delete.
   Re-query the branch API and confirm `protected: true`.
2. Under Settings → Environments create `catalog-production`, restrict
   deployments to `main` or protected branches, enable Required Reviewers
   and Prevent self-review. Capture non-secret screenshots/JSON of controls.
3. Set environment secrets `CATALOG_ED25519_PRIVATE_PEM` and
   `CATALOG_ED25519_PUBLIC_PEM` using an approved key ceremony.
   Do **not** paste secret contents into chats, issues, PRs, Actions summaries
   or screenshots.
4. Separately approve the SHA-256 **of the raw 32-byte Ed25519 public key**
   and register it as environment variable
   `CATALOG_ED25519_TRUST_SHA256` (lowercase 64-character hexadecimal).
   The same raw key must be pinned in the signed Analyzer build from an
   out-of-band verified source. A matching fingerprint proves key identity,
   not the custody/security of the private key.
5. Execute `scripts/verify_trust_anchor.py` with the approved PEM public
   key and approved fingerprint in an authorized secure terminal. It must
   output `APPROVED TRUST ANCHOR MATCH: PASS`.
6. Re-run the audit with read-only administrative token, independently
   verify reviewer identity and `main` protection; archive audit timestamps
   and immutable evidence (without secrets). Only a subsequent explicit
   security approval may release the production publication hold.

### Additional hard stop added to publisher

`publish-signed-catalog.yml` now queries the `main` branch API and
stops when `protected` is not `true`. It also requires
`CATALOG_ED25519_TRUST_SHA256` and compares the expected fingerprint
against the public signing key before packaging. It cannot independently
prove that environment reviewers are correctly configured, and therefore
manual administrator verification remains a mandatory prerequisite.
