# CPA Management Center — Siriusrry

Personal builds of [CLI Proxy API Management Center](https://github.com/router-for-me/Cli-Proxy-API-Management-Center), retaining the official single-file `management.html` delivery format. This repository maintains two small source patches and the build/release pipeline; it is not the CPA Go backend.

[Latest release](https://github.com/Siriusrry/cpa-management-center/releases/latest) · [Daily workflow](https://github.com/Siriusrry/cpa-management-center/actions/workflows/update.yml)

## Customizations

- Codex quota cards show the authentication file's priority immediately after the manual reset count, using the authentication-file badge appearance.
- Zero and negative safe integers are displayed; absent/invalid values are hidden. Narrow cards wrap naturally. Other providers and authentication-card quota bodies retain their existing behavior.
- Quota-card titles and quota-window labels/tooltips show the email using the authentication page's identity helper; missing email displays `—`. Full filenames stay internal for requests and cache keys.
- Both priority and email display are maintained on every upstream update.
- Management Center version ends with `-Siriusrry`, e.g. `v1.22.14-Siriusrry`.

## Daily update contract

At **09:23 Asia/Shanghai (01:23 UTC)**, the workflow reads the latest official stable Release once. It processes only that snapshot, not every intermediate Release or unpublished `main` commit. With no new version or local revision, it skips dependency installation and builds. GitHub scheduling can be delayed or occasionally dropped; manual dispatch is also available.

1. Resolve the upstream Release to an exact commit.
2. Apply `patches/*.patch` in order, with checked Git patch context; conflicts fail without guessing resolutions.
3. Install the locked upstream dependencies with the reviewed Bun version; run all upstream tests, lint, TypeScript compilation and build.
4. Package HTML, corresponding patched source, license, build metadata and SHA-256 checksums.
5. Upload to a draft Release, download and byte-verify every attachment, then publish as the latest stable Release.

Any conflict, validation failure, permission problem or failed upload makes Actions **fail**. No `continue-on-error` is used for these gates. The last successful public Release remains available. Your existing GitHub Actions failure-email preference controls notifications; scheduled runs are associated with the workflow's scheduling actor. No email credential or third-party notification service is needed.

The official verification suite does not certify every upstream feature against a live CPA backend. Upstream API incompatibilities may require manual review or a backend update.

## Preventing the 60-day inactivity suspension

A separate maintenance job runs **before** source merging and validation. Every **25 days**, it commits `.maintenance/heartbeat.json` with the actual check time to `main`. This creates repository activity even when upstream has no releases or the customization has been failing, while avoiding daily commit noise. `[skip ci]` avoids an extra push CI run; subsequent scheduled runs still execute.

The maintenance job needs `contents: write`. Removing that permission or blocking its direct push fails the workflow. This mechanism addresses GitHub's 60-day repository-inactivity rule; it cannot resurrect workflows manually disabled, an archived repository, or a schedule that never runs for other reasons. Re-enable the workflow from Actions if needed.

## Manual maintenance

- Run **Actions → Update and release management HTML → Run workflow** to check now.
- On a conflict, inspect the selected upstream version and failing patch in the run log. Adapt the patch on that exact upstream source and run the workflow again.
- If changing build inputs for an already published upstream version, increment `revision` in `build-config.json`. Revision 2 produces `v1.22.14-r2-Siriusrry`. Published attachments are immutable; only incomplete drafts can be retried.
- If upstream incorporates either customization itself, remove/adapt the patch after reviewing behavior.
- If upstream changes its declared Bun version, the workflow intentionally stops until `build-config.json` is reviewed.
- `build-info.json` records official tag/commit, pipeline commit and build-input fingerprint. `source.tar.gz` contains the corresponding patched source, including original licensing.

## CPA configuration

To opt a CPA installation into these builds:

```yaml
remote-management:
  panel-github-repository: "https://github.com/Siriusrry/cpa-management-center"
  disable-auto-update-panel: false
```

Publishing this repository does not itself change any running CPA installation. Deployment configuration and rollback belong to that installation's deployment controls.

## Local validation

Requires Python 3, Git, GitHub CLI, Node.js 24 and Bun matching `build-config.json`.

```sh
python3 -m py_compile scripts/pipeline.py scripts/keepalive.py
python3 scripts/pipeline.py plan --repo Siriusrry/cpa-management-center
python3 scripts/pipeline.py prepare
# In .work/source: bun install --frozen-lockfile, then VERSION=<planned version> bun run verify
python3 scripts/pipeline.py package
```

Use a fresh `.work/source` for each preparation. Build outputs and dependencies are ignored. No production credentials or authentication files are used in verification or Releases.

## License

Upstream is MIT, copyright Router-For.ME; its notice is retained in `LICENSE`, the HTML distribution and the corresponding source. Custom automation and modifications are also provided under MIT, copyright 2026 Siriusrry.
