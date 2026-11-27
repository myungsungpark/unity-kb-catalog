# 6 — Signed GitHub Release Catalog distribution (implementation candidate)

## Status
Draft implementation only. No Stable Release is authorized. The repository's
main catalog remains `draft` and cannot be published by `release_catalog.py`.
This branch intentionally does not include a production private key, public
key, release publication workflow, or an Analyzer integration.

## Artifacts
- `unity-kb-catalog.json` — exact release payload
- `release-manifest.json` — canonical JSON metadata with SHA-256 digest and version
- `release-manifest.json.sig` — raw Ed25519 signature over manifest bytes

The Analyzer must ship with an independently provisioned pinned public key.
Keys delivered as Release assets must NOT be trusted as root of trust.
The private signing key must be held in a protected, approval-gated CI secret
(or external signing service), never inside this repository.

## Guardrails
- Restrict releases to reviewed, validated, explicitly `released` catalogs.
- Protected/tagged release workflow with environment approvals, minimal permissions.
- Run original catalog validator and all regression tests prior to status transition.
  The current validator requires `draft` and must be updated to support an
  explicitly gated `released` publishing state before any official release.
- Client trusts a fixed repo, versioned tag and pinned key; it rejects drafts,
  prereleases, wrong channel, incorrect signature, hash mismatch and downgrades.
- Catalog incident matching remains disabled; KB matching stays Analyzer-owned.
- Backups and same-directory atomic replacement protect against ordinary failures.
  Robust Windows filesystem locks, concurrent updaters, fsync directory durability,
  power-loss recovery, restored-backup authentication, and application cache reload
  require Analyzer-side integration. These are *not* certified by this branch.
- Rolling back an installed release should use a previous known-good and
  independently authenticated payload; never bypass the signature requirement
  just to accept an older version.
- The fetch helper requires an *explicit* tag. Latest-channel discovery and
  release tag-to-version binding are future work. Callers must not treat an
  unsigned GitHub API response as proof of the correct signed version.

## Validate
```bash
python -m pip install -r requirements-release.txt
python -m unittest discover -s tests -p 'test_release_distribution.py' -v
```

The 3-job CI runs the same eight scenarios on isolated runners. It is not
three implementation-independent reviews and not a Windows acceptance test.

## Pending before production
1. Approve production key management, rotation and trust-anchor distribution.
2. Add signed release/version binding and anti-replay / downgrade controls.
3. Make publisher and release workflow enforce protected tags, verified commits,
   successful independent tests, and reviewer approval.
4. Complete crash-safe Windows x64 Analyzer integration and recovery tests.
5. Run three independently evaluated verification passes; archive run IDs,
   signed asset hashes, and exact tested commit before a Stable release.
