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

## Test ownership and execution

`Python/tests/ide/` keeps project persistence, shared-buffer lifetimes, Markdown
integration, navigation, tree presentation and confined drag coverage. Pure
`search_files` masks, exclusions, regex and live-buffer cases live in commonUtils'
`tests/browser/test_search.py`; the IDE Find in Files tests retain real worker,
preview, cancellation, project exclusions and unsaved-buffer navigation checks. The unused
`analysis.search_project` predecessor has been removed; Find in Files uses the
shared search owner and Go to File retains `analysis.project_files`.

Run the daily selection with `python3 dev.py test desktop 'test_ide*.py' --profile daily`.
The default full profile additionally runs the 1,000-line theme-switch case and
48 synthetic plus 24 QTest side-drop matrix. Daily tests retain both side-drop
receivers/directions, QTest input, merge/split, cancellation and group-cap checks.
Non-autosave fixtures explicitly disable autosave; dedicated autosave/change-marker
coverage remains in `Python/tests/editing/test_editor_changes.py`. The IDE owner
selection includes that file: `python3 dev.py test-owner ide --profile daily`.
Run the relocated shared cases with `python3 dev.py test shared test_search.py`.

Find in Files checks reject nonempty stale results both while a newer request
is pending and after closing; a superseded preview cannot replace the newly
selected file. Gesture checks preserve unsaved text, cursor and
undo through both synthetic and QTest input; the group-cap case also verifies
that a rejected drop has no target or preview.

Browser discovery checks need native filesystem notification access even with
`QT_QPA_PLATFORM=offscreen`. A restricted macOS sandbox can populate the initial
rows but miss later file creations. Run the isolated suite with notification
access before treating that timeout as an application regression; keep the real
automatic-update assertion. Failure diagnostics include the expected and actual
rows and active filter. Git status tests explicitly refresh staging changes but
retain an automatic timer-driven check when a modified file becomes clean.

These host checks validate Qt integration and document state, not native window
manager behavior or visual appearance on each supported desktop platform.
