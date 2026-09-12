# Management Center build repository

- Owns public customization patches, automation and release metadata only. Never copy private backend source, deployment config or credentials into this repository.
- Upstream source is prepared under ignored `.work/source` at an exact stable-release commit. Read its AGENTS.md before source changes and retain upstream licensing. Do not import its workflows into this repository's `.github`.
- Maintain these customizations across upstream releases: Codex priority badges and email quota-card/window labels with full filenames retained on hover; read the supplied email directly without missing-email branches. Use only `<official-version>-Siriusrry` for display and release tags, with no extra revision suffix.
- Default quota ordering keeps provider groups in QUOTA_TAB_ORDER, then priority ascending within each group, retaining original order for ties. Keep this in the existing sort function and full-index three-way patch.
- Keep the patches small. Reuse upstream API fields and i18n. Preserve the single HTML and hash routing.
- Verification: upstream `bun run verify`, single-file/version checks and Release upload verification. Do not add duplicate display edge-case tests, theme/mobile matrices, extra browser frameworks or checks unrelated to these display changes.
- Never publish personal emails, local paths, deployment details, live configuration, credentials or user screenshots. Use the public GitHub handle and noreply commit email.
- Failure gates must fail Actions and preserve the latest successful public Release. Use a small full-index patch with an explicit upstream base and Git three-way merging; never force a conflicting side or ignore validation failure. Same-version rebuilds use staged publication with rollback.
- Maintenance commits every 25 days must stay independent of source patch/build success.
- Build-input fingerprints identify rebuilds internally; do not append revision numbers to the visible version.
- AGENTS.md and CLAUDE.md are byte-identical; update both together.
