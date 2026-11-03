# Notes Library feature and desktop navigation brief

Status: Implemented; validation scope is recorded in the [feature development guide](../features/notes_library/development/development.md). Requested November 2, 2026.

Give Notes Library its own desktop destination immediately below Documents and
extract it from Text Editor into `features/notes_library`. The destination must
own open library sessions, rather than send them back into Documents. Keep one
feature entry: search, calendar, links, data views and embedded editors remain
parts of Notes Library.

## Problem and intended outcome

Notes Library currently registers as a Text Editor folder action. Opening one
creates a `TabbedNotesLibrary` and publishes it through the generic document host.
Its navigator, document groups, provider leases, search, calendar and mutations
already constitute a workspace, but users reach it through folder actions or
document history.

Selecting **Notes Library** in the desktop rail should open a dedicated page for
opening and switching libraries. Opens from Workspaces, browser offers and
favourites should select this same destination. Ordinary standalone documents
retain their existing editor and Documents routes.

## Desktop experience

- Place a distinct library/notebook glyph directly below Documents, before the
  existing workspace destinations. Use the accessible name **Notes Library**, a
  tooltip and the normal selected state. Keep its position stable across feature
  combinations and support the rail's existing scrolling behavior.
- With no library open, show a short explanation and **Open Library**. Accept an
  ordinary local folder without requiring `.obsidian`. Offer configured local and
  LocalCrypt copies through existing selection/unlock flows. Cloud-only folders
  retain the existing download or sync guidance.
- Use an outer library session selector. Retain Files, Calendar, Search, Links and
  the existing document tab groups within each library. Switching preserves its
  selection, drafts, history and splits. Avoid another document tab layer around
  the existing groups.
- Reopening the same provider context and normalized root focuses its existing
  session. Equal labels alone do not identify the same library. Favourite opens
  also select the referenced note.
- Destination switching leaves sessions alive. Note close, library close and app
  quit retain save/discard/cancel behavior and cooperative worker shutdown.
- Preserve library detachment through the shared workspace machinery. Reopening a
  detached library presents its window; reattachment returns it to Notes Library.
  Documents counts and its overlay exclude library sessions.
- Expose the destination through the existing Home launch catalog and command
  routing. Do not add it to the Documents editor chooser as a second launch path.

Initial delivery needs no new recursive discovery service or restart restoration.
Existing folder detection and favourites remain entry points. Navigation retention
must not introduce persistence of unlocked providers or decoded private paths.

## Ownership and dependency decisions

| Owner | Responsibility after extraction |
| --- | --- |
| `features/notes_library` | Library model, containment, links, mutations, data views, library desktop/mobile UI and folder actions |
| `features/text_editor` | Standalone text/code editing, browser activation, preferences and recovery |
| `services/documents` | Shared provider access, resource sessions, credential policy, catalog storage and Logistics document authoring adapters |
| `desktop` | Rail placement, destination activation, application hosting and shutdown |
| `mobile` | Existing Documents discovery, navigation and platform composition |
| commonUtils | Reusable Markdown/code editing, search, provider, tab and workspace mechanisms |

Notes Library must work with Text Editor disabled. Its desktop embedded source
editor already uses commonUtils directly. Mobile library Markdown shares authoring
modules with standalone documents; establish a shared owner before moving library
adapters. Logistics-specific shared authoring belongs in document services;
reusable mechanisms belong in commonUtils. Do not add another user-facing feature
to resolve these imports.

Notebooks is an optional integration for `.rmdoc` drawings. Declare the relationship
and gate opening/creation on availability and enabled state. A disabled Notebooks
feature must leave Markdown/text libraries usable and explain unavailable drawing
actions. Apply the application's retained-document policy to drawings already open.

Rclone/LocalCrypt is optional storage integration through document services. Local
libraries must work with Rclone disabled. No Obsidian application or feature is
required; `.obsidian` is a detection marker. Preserve the existing bounded data
view runtime, trust behavior and resource limits without adding an index.

## Extraction source map

Paths below are relative to `Python/` and describe owners before extraction.

| Area | Current source and required change |
| --- | --- |
| Registration | Move the folder contribution from `features/text_editor/contributions.py` into a lazy Notes Library declaration with its own page contribution |
| Portable model | Extract `features/text_editor/notes.py`, `notes_links.py`, `library_files.py`, `dataview.py` and `dataview_script.py` with their library-specific helpers |
| Desktop presentation | Extract the library owners in `features/text_editor/ui/`: `notes_library.py`, `library_workspace.py`, `library_panels.py`, `library_icons.py`, `library_text.py`, `dataview.py` and `notes_offer.py` |
| Session opening | Replace the generic `show_document` handoff in `ui/notes_library.py:open_notes` with one authoritative library host; preserve standalone use when no application host exists |
| Navigation | Extend `desktop/sidebar.py`, `desktop/navigation/catalog.py` and main-window feature-page composition with explicit placement after Documents, independent of alphabetical feature sorting |
| Catalog and locations | Update `desktop/document_catalog.py`, `desktop/location_context.py` and `desktop/documents.py` assumptions about library hosting while preserving references and location labels |
| Mobile library | Extract `features/text_editor/mobile/notes_library.py` and its library document, text, panels, tools, drag, swipe and data view adapters; separate shared authoring before moving it |
| Mobile host | Update library imports/gates in `mobile/notes_discovery.py`, `notes_actions.py`, `obsidian.py`, `hub_ui.py`, `favourites.py` and `composition/presentation.py` |
| Packaging | Update owning `mobile_sources.json` declarations together; include moved modules exactly once and exclude desktop-only imports |

Audit remaining references during implementation. Preserve the existing working
changes in these owners; extract their current behavior without reverting to an
older baseline or renaming unrelated files, saved keys or settings.

## Session lifetime and privacy

All entry points must reach one authoritative host per library. Prefer extending
the existing document/workspace hosting contract with explicit destination
ownership over copying Documents' detach, close and worker machinery. Keep
registration lazy and portable domain modules independent of Qt and Toga.

Provider leases remain scoped to each library and child tab. Closing one session
must not revoke siblings. Lock/revocation clears private names and content in
attached and detached windows, retires searches/data views and prevents late
callbacks from publishing. Session identity distinguishes credential contexts
without persisting secrets or decoded private names. Reuse encrypted catalog
storage and existing reference formats.

Save failure or newer input during a save must prevent deferred close/navigation.
Disabling the feature removes new entry points while retaining open owners under
the existing lifecycle. Keep those sessions reachable for saving and closing;
reenabling reuses them. Never hide the only route to a retained draft.

## Settings and compatibility

Introduce stable feature ID `notes_library` and one independent enable setting.
For installations without an explicit Notes Library preference, inherit the old
Text Editor state once, then allow independent settings. Respect preference
layering, apply equivalent semantics on desktop/mobile and avoid rewriting
unrelated defaults.

Preserve favourite/recent `editor='notes'` references, roots and document identities.
Route them through the new host without requiring recreation. Migrate internal
imports to the new owner; retain compatibility imports only for actual consumers
and avoid duplicate registration.

Mobile navigation stays as it is. Only library-specific gates change from
`text_editor` to `notes_library`; standalone Markdown/text retains its current
controls. Test both independent combinations. The new feature must not indirectly
enable Text Editor through a shared authoring import.

## Delivery sequence

1. Audit imports, feature gates, catalog consumers and payload declarations.
   Establish the shared mobile authoring boundary and preference migration cases.
2. Extract portable and platform library owners with lazy registration. Update
   imports/manifests together and run existing library/authoring regressions.
3. Add the desktop destination and session host. Route chooser, folder actions,
   browser offers and favourites through it; implement switching, deduplication,
   close and detach using existing workspace contracts.
4. Add the rail glyph/position, Home routing and retained-session behavior during
   feature toggles. Preserve `DestinationRail.tools_menu` and the Misc glyph.
5. Validate the matrix below and update implemented-behavior documentation.

## Acceptance and validation

| Area | Required result |
| --- | --- |
| Navigation | Icon immediately below Documents across feature combinations/window heights; selection, keyboard activation, tooltip and accessible label agree |
| Entry paths | Chooser, LocalCrypt unlock, Workspaces, browser offer, Home and old favourites reach the same destination and reuse matching sessions |
| Multiple libraries | Identically named roots stay distinct; reopening focuses the right session; switching preserves drafts, navigation and splits |
| Routing and detach | Standalone files stay in Documents; library sessions leave its counts/overlay; detached libraries focus and reattach correctly |
| Editing and shutdown | Independent drafts, failed saves, cancelled close, save-time typing, mutations and app quit preserve data and retire workers before releasing leases |
| Privacy | Local works without Rclone; LocalCrypt works unlocked; lock during open/search/save clears every affected window and rejects stale results |
| Feature controls | Text Editor and Notes Library work independently; preferences migrate once; unavailable notebooks have clear behavior; retained sessions remain reachable |
| Mobile | Existing discovery/favourites/navigation work; standalone authoring works with Notes Library disabled; library editing works with Text Editor disabled |
| Packaging | New owner is discoverable with lazy registration; mobile manifests include required modules without Qt imports |

Extend desktop `test_notes_library_desktop.py`, `test_notes_library_tabs.py`,
`test_markdown_library_modes.py`, `test_text_editor_dataview.py` and relevant
application navigation, preference and boundary tests. Add session routing,
identity, detach and shutdown cases. Keep test ownership/manifests consistent;
do not relocate suites solely to match import names.

Run relevant mobile Notes Library, Markdown authoring and feature-state suites.
Shared authoring moves also need focused native library and standalone Markdown
smokes on disposable iOS/Android targets. Inspect the actual Qt rail, empty state,
multiple libraries and detach behavior. Record host and native scope separately.
Follow the [validation workflow](testing.md) and managed build/device lifecycle;
save raw evidence under ignored test results and remove temporary QA apps/devices.

## Documentation and completion

Once implemented, create `docs/features/notes_library/` guides with same-named
landing pages and explicit parent links. Move library-specific material from Text
Editor guides and preserve useful links from old locations. Keep shared contracts
in systemic guides and commonUtils API details in commonUtils. Update the root
README for the new destination while preserving its exact Ally Tools sentence.

Complete when all desktop library entry paths use the new destination, feature
independence works on both platforms, existing references remain valid and the
acceptance matrix passes with its validation scope recorded. A rail shortcut
that still opens libraries in Documents does not satisfy this brief.
