# 6-A — Production release publishing workflow (NOT YET APPROVED)

## Workflow
`.github/workflows/publish-signed-catalog.yml` is deliberately manual-only and
will be available through workflow_dispatch after this workflow is merged to
the default branch (`main`). Never enable automatic stable publication on pushes.

### Required GitHub configuration (manual admin steps)
1. Protect `main` with required reviews and required successful CI checks.
2. Create an environment named **catalog-production** in
   Settings > Environments, restricted to protected `main`, with at least
   one **required reviewer** independent of the publisher. If the account
   plan/repository settings cannot enforce environment reviewers, **do not
   publish**; use a repository/organization deployment control with approvals.
3. Set the following **environment secrets**, not repo files or workflow code:
   - `CATALOG_ED25519_PRIVATE_PEM`: PEM private signing key.
   - `CATALOG_ED25519_PUBLIC_PEM`: matching PEM public key; its fingerprint
     must be independently approved and embedded in the shipped Analyzer.
4. Establish a key-rotation/revocation process. A GitHub-only public key
   download must never be used as the Analyzer root of trust.
5. Configure permissions so only the approved publisher workflow may write
   releases/tags, enforce immutable release tags where possible, and archive
   signed asset digests and CI run evidence.

### Release process
- Review and approve the immutable exact `main` commit.
- Run Actions > 6-A Publish Signed Catalog Release > Run workflow on `main`
  with `version` equal to `manifest.json` and `confirmation=PUBLISH`.
- Three isolated CI jobs check original draft validator, legacy regression,
  signed distribution regression and exact candidate version.
- Reviewer approves the `catalog-production` environment gate.
- Publisher rechecks exact source draft and prepares `released` output in a
  temporary directory without modifying the repository.
- CI signs `release-manifest.json` using protected Ed25519 private key,
  checks against independently configured trusted public key, and verifies
  the release package.
- CI creates a **draft** Release at `catalog-vX.Y.Z`, downloads all 3
  assets back from GitHub, byte-compares them and verifies signature, hash,
  signed tag, version and minimum Analyzer version.
- Only after download verification does it promote the Release to public
  stable. Failure leaves it draft for investigation. Duplicate release
  versions/tags are blocked.
- The `main` Catalog remains `draft` until an explicit separately reviewed
  migration policy is approved. No live Analyzer update is triggered here.

### CI coverage / remaining gates
The 3 runs use separate GitHub-hosted runners and ephemeral keys for test
cases. They are **not** independent implementations or a complete security
review. Production authorization additionally requires: genuine signed
artifact review, Win64 Analyzer pinning to the published trusted key,
anti-replay/downgrade and authenticated rollback, concurrent-update locking,
power-loss recovery, and published-asset re-verification on a Windows host.

### Cleanup / incident policy
Do not delete an unknown failed draft automatically; first inspect its commit,
signed hashes and logs. Never overwrite an existing stable version or reuse
an existing tag. If the publisher fails after draft creation, keep it
non-public and require manual incident triage. Never move a signed stable tag
to a different commit.
