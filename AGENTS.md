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
