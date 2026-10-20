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
Update `Python/features/<owner>/docs/user/` for desktop workflows,
`docs/user_mobile/` within mobile feature owners for mobile workflows, and their
`docs/development/` for feature architecture/contracts. Systemic guides belong in
root `docs/user/`, `docs/user_mobile/` and `docs/development/`. Update the root README for setup or
major capabilities. Preserve `user_docs/index.md` as an in-app compatibility link.
Systemic Core UI and Folder Hub guides belong in the Logistics wiki; Bulk Rename
keeps its documentation beside its existing `ui_new` owner.
Describe implemented behavior and verify consequential operations against source/tests.
Shared commonUtils APIs are documented in their own repository, not copied here.

`Python/features/emulation` is an ignored link into a separate repository.
When explicitly asked to document that local project, resolve the link, read its
own AGENTS.md and keep feature/user/developer docs and commits there. Never stage
those files in Logistics, replace the link with a directory, or include them in
public documentation navigation/releases. Logistics documentation may explain only
its host integration, configuration and workflow boundary. Emulator capabilities,
setup and implementation belong to the linked project's own guides.

Documentation wikis use `docs/docs.md` as their scope landing. Each nested folder
has a same-named landing page (`banana/banana.md`), with explicit links to every
child page. Every Markdown page begins with an H1, after optional YAML properties.
Keep package README and `user_docs/index.md` compatibility entries as short links.
