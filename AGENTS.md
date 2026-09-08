# Management Center build repository

- Owns public customization patches, automation and release metadata only. Never copy private backend source, deployment config or credentials into this repository.
- Upstream source is prepared under ignored `.work/source` at an exact stable-release commit. Read its AGENTS.md before source changes and retain upstream licensing. Do not import its workflows into this repository's `.github`.
- Maintain two functional customizations across upstream releases: Codex priority badges and email-only quota-card/window names (including tooltips; `—` when email is absent). Keep the Siriusrry build suffix.
- Keep the patches small. Reuse upstream API fields and i18n. Preserve the single HTML and hash routing.
- Verification: upstream `bun run verify`, single-file/version checks and Release upload verification. Do not add duplicate display edge-case tests, theme/mobile matrices, extra browser frameworks or checks unrelated to these display changes.
- Never publish personal emails, local paths, deployment details, live configuration, credentials or user screenshots. Use the public GitHub handle and noreply commit email.
- Failure gates must fail Actions and preserve the latest successful public Release. No forced conflict resolution, ignored validation failure, or replacement of published assets.
- Maintenance commits every 25 days must stay independent of source patch/build success.
- Increase build-config.json revision when changing published build inputs for the same upstream version.
- AGENTS.md and CLAUDE.md are byte-identical; update both together.
