# Project IDE

[User guide](../user/user.md) · [Architecture](ide.md)

`projects.py` owns the versioned registration store. `ui/page.py` manages project
settings and retained tabs. `ui/workspace.py` owns canonical document paths, groups,
workers, close decisions and restoration. `ui/browser.py` wraps the shared lazy
filesystem model. `ui/documents.py` owns shared text buffers and independent CodeEdit views;
`ui/navigation.py` presents `analysis.py`'s background Jedi and bounded scan results.
No IDE import depends on the standalone Text Editor. `ui/git_status.py` optionally
uses the Git backend for read-only project-tree colors independently of Git UI
activation or repository registration.

Project containers reuse shared Workspace sizing, detachment and menu routing.
Internal editor gestures use ScopedTabBar, confined to each project’s editor
splitter; file tabs never become floating windows. See the user guide for menus
and left/center/right snapping.

## Desktop presentation

Desktop widgets and controllers live in feature-owned `ui/`. Registration stays lazy; portable domain modules do not import this package. IDE/Text Editor change-marker and hunk integration is shared through `services/editors/ui/`.

## Workspace checkpoint admission

`ProjectStore` reads at most 4 MiB plus one byte before parsing. It validates
project records, unique identifiers, the open-project list and active identifier
before publishing any loaded state. A malformed checkpoint leaves an empty store
with a visible error and prevents saving over the original. Duplicate open IDs
remain deduplicated and stale string IDs remain filtered as before. The schema
version, project fields and JSON layout are unchanged. `test_ide.py` covers
malformed structures, partial admission, conflicting writers and round trips.
