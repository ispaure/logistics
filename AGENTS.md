# Repository instructions

## Root README: optional Ally Tools acknowledgement

Keep the root `README.md`'s Ally Tools coverage limited to this single sentence:

> Additional emulator tools are available on request through ispaure’s **ally-tools**.

Preserve it during README rewrites. Do not expand it into a feature row, section,
emulator list, setup guide, dependency description or integration explanation.
Do not add links to Ally Tools' repository or documentation, including Markdown
files accessed through a local feature symlink/junction or sibling checkout.

Local files under `Python/features/emulation` belong to a separate repository;
they are not bundled Logistics documentation and may be absent in public clones
and releases. Keep Ally-specific documentation in Ally Tools. This README rule
applies to future automatic documentation updates unless the user explicitly
changes the boundary. Existing authorized launcher/integration code remains
within scope for technical maintenance.

## Navigation fallback

Keep `DestinationRail.tools_menu` and the existing `tools` (Misc) icon drawing.
They are reserved for future nested destinations even when all current features
have their own rail buttons. Do not delete this code or glyph unless the user
explicitly asks for its removal.

## Boox test-app cleanup

After testing on the user's Boox, uninstall temporary Logistics test, probe and
QA apps installed for that work. Save needed test evidence before uninstalling.
Verify that the only remaining Logistics package is the main app,
`io.github.ispaure.logisticsmobile`. Preserve that app and its data; never
uninstall it or clear its storage during cleanup. If cleanup cannot finish,
report the remaining test packages rather than silently leaving them installed.
Keep test apps only when the user explicitly requests it.

## Documentation ownership and maintenance

Read [the developer index](docs/development/development.md) before structural changes.
All substantive Logistics documentation belongs in the root `docs/` wiki.
Systemic guides use `docs/user/`, `docs/user_mobile/` and `docs/development/`.
Feature guides use `docs/features/<owner>/user/`, `user_mobile/` and `development/`;
Bulk Rename uses `docs/features/bulk_rename/`. Keep source/package README and
`user_docs/index.md` entries as short compatibility links. Update the root README
for setup or major capabilities. Shared APIs are documented in commonUtils' own
root `docs/`, rather than copied into Logistics.

`Python/features/emulation` is an ignored link into a separate repository.
When explicitly asked to document that local project, resolve the link, read its
own AGENTS.md and keep its guides and commits there. Never stage those files in
Logistics, replace the link with a directory, or include its internals in public
navigation/releases. Logistics may document only its host integration boundary.

The wiki root is `docs/docs.md`. Every nested folder has a same-named landing
(`banana/banana.md`) with explicit links to every child page. Every Markdown page
begins with an H1 after optional YAML properties; that title labels its viewer row.
Describe implemented behavior and verify consequential claims against source/tests.

Keep raw test evidence (screenshots, recordings, reports and one-off probe copies)
under ignored `test-results/` or `mobile_build/logs/`, outside documentation wikis.
The historical archive is local-only at `test-results/mobile-evidence/`; never add
it or the legacy `docs/development/mobile-evidence/` location to Git, release
packages or mobile offline help. Keep reusable test drivers/fixtures tracked in
their test owners, and retain concise validation scope in developer guides.
Public documentation must not link to local-only artifacts.

## Branch workflow

Work on the current development branch by default. Create a separate branch only
when there is a concrete reason, such as isolating concurrent work or a risky
experiment; do not create `codex/*` branches automatically.
