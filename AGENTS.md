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

## Documentation ownership and maintenance

Read [the developer index](docs/developer/README.md) before structural changes.
Update `Python/features/<owner>/user_docs/README.md` for user-facing behavior and
`docs/developer/` for architecture/contracts. Update the root README for setup or
major capabilities. Preserve `user_docs/index.md` as an in-app compatibility link.
Core UI and Bulk Rename guides remain alongside their existing `ui_new` owners.
Describe implemented behavior and verify consequential operations against source/tests.
Shared commonUtils APIs are documented in their own repository, not copied here.

`Python/features/emulation` is an ignored link into a separate repository.
When explicitly asked to document that local project, resolve the link, read its
own AGENTS.md and keep feature/user/developer docs and commits there. Never stage
those files in Logistics, replace the link with a directory, or include them in
public documentation navigation/releases. Logistics documentation may explain only
its host integration, configuration and workflow boundary. Emulator capabilities,
setup and implementation belong to the linked project's own guides.
