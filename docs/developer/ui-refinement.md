# UI refinement validation — 2026-10-11

## Delivered behavior

| Owner | Change |
| --- | --- |
| IDE projects | Shared Workspace containers, equal-width project headers, overflow, retained independent project state, project detachment and a + menu even when empty. Opening an already-open registration from another container moves its retained pane to the requesting container. |
| IDE editors | Up to three horizontal groups. Header drops insert/reorder; content center merges; left/right quarters create groups. Existing buffers survive moves; duplicate views merge; empty groups disappear. Escape/outside drops cancel and cannot create a floating window or cross projects. |
| IDE browser/layout | Font-scaled panel minimum widths, noncollapsible splitters and compact outer spacing. |
| IDE menus | File, Edit, View, Navigate and Project reuse workspace menu publication; shortcuts operate within the owning project and the current editor. File includes Save All and Close Project. Settings/source paths are contextual project commands. |
| File Browser | One docked tab retains its header. Detached single-tab containers retain local + controls. The last normal browser tab still cannot close or detach. |
| Documents | Existing workspace sizing, close ownership and local detached creation retained and regression-tested. |
| Git | Repository panes use the shared detached-container policy; opening a new repository from a detached pane targets that pane's container. Shutdown checks all containers. Views without an alternate controls row retain their single header so + remains reachable. |
| Bulk Rename | Compact spacing, resizable/hideable rules, a responsive rule grid, Scope and Rule presets menus, readable minimum filename-column widths. Hiding rules does not disable or reset them. |
| Text Editor | Full-area document layout with reduced outer padding; existing menus, document ownership and contextual disk-change controls retained. |
| Markdown | Format menu shares the existing navigation row. Formatting, heading, list and table operations no longer reserve a second toolbar row. |

Shared commonUtils changes are documented in `ui/scoped_tabs.md` and the Markdown
component guides in that repository. ScopedTabBar reuses workspace drop geometry,
but never enters the native window-drag controller. Hosts own document lifecycle,
group limits and close policy. Workspace now emits tab-change notifications after
reordering and retains the only + control when a view supplies no alternate row.

## Validation

Git hunk lists explicitly align cards to the top instead of using a trailing
stretch item. This keeps the 10-pixel spacing when native button metrics make
headers wrap. The hunk suite retains native-style coverage and repeats its five
workflows with the Windows style and a 13-point UI font, reproducing the spacing
failure on macOS before the fix. All ten focused tests pass locally; an additional
Windows/Fusion probe passed at UI sizes 9, 11, 13 and 16. These focused results are
separate from the earlier full-suite results below.

Environment: macOS 26.6.2 ARM64, Python 3.12.2, project PySide6 environment.

- Logistics isolated suite: **857 tests across 79 modules; zero failures**.
- commonUtils isolated suite: **675 tests across 92 modules; zero failures**, one
  expected case-sensitive-filesystem skip on this volume.
- Focused shared workspace/container/gesture stage: 42 tests passed.
- Markdown: 94 tests across six isolated modules passed.
- Clean committed snapshot: all 23 IDE tests across two isolated modules passed,
  using archived Logistics/commonUtils commits without uncommitted source changes.
- Final focused checks passed for detached Git creation, a 680-pixel-wide Bulk
  Rename window, retained rules, readable filename columns, browser single-tab
  policy and reopening a project into the requesting detached container.
- Native Cocoa/AppKit checks observed File/Edit/View/Navigate/Project menus while
  switching projects and after detaching a project. Maximize/restore preserved
  browser panel minimums. These ran in a temporary test application.
- Visual inspection used Logistics' actual Slate light/dark themes at large and
  narrow sizes for IDE, Bulk Rename and Markdown. Three IDE editor columns retain
  usable minima and horizontal editor scrolling at narrow widths.
- Repository Ruff and both repositories' diff whitespace checks passed.

Commands used the project interpreter, `PYTHONPATH=Python` and
`QT_QPA_PLATFORM=offscreen`, with `tests/run_regressions.py <test-directory>
--isolate-modules`. Native menu checks used `QT_QPA_PLATFORM=cocoa` and inspected
only the temporary test application's AppKit menu. Qt CPU detection required
running tests outside the filesystem sandbox.

The full working-tree suites and native Cocoa run include existing, concurrently
edited native-menu/browser/navigation work. Those changes were preserved and were
not included in this task's commits. The clean committed IDE snapshot was tested
separately offscreen. Late narrow-layout and new policy tests were also run as
focused checks after the full-suite run began.

## Limits

- Native Windows/Linux desktop interaction was not tested. Qt routing tests cover
  their menu branches on macOS; this is not native platform validation.
- Project sessions reopen into the main container; detached OS-window geometry is
  not persisted. Each project's editor groups, files and view positions remain
  part of its existing session state.
- Internal editor groups remain horizontal and capped at three. Side drops at
  the cap are rejected only when an additional group is needed. Single-file
  columns can be repositioned; empty target columns are reused.
- Existing storage, analysis and recovery limits in the IDE guide are unchanged.

## Commits

Logistics:

- `98eefb9` — shared project containers, confined editor snapping, menus and tests.
- `33561ff` — compact feature layouts, browser policy and detached creation ownership.
- `0fae34a` — readable filename columns in narrow rename windows.
- The validation record is committed separately after these implementation stages.

commonUtils (Logistics pins `a6cc899`):

- `6e5f904` — confined tab gestures, shared drop geometry and accessible workspace controls.
- `fd40356` — Markdown formatting consolidated into its navigation header.
- `a6cc899` — keyboard focus for Escape cancellation during confined dragging.

The root README's Ally Tools acknowledgement and the reserved Misc/tools rail
navigation code were preserved.

## Placement edge-case audit

A follow-up review found and fixed placement defects not caught by the initial
accept/reject assertions:

- Drag preview bands were QSplitter children and could become hidden layout panes.
  They now belong to tab widgets, so splitter indices match editor-group order.
  Previously saved alternating hidden-pane widths are recovered during restore.
- Native side splitting could move the target group or tabify instead of splitting.
  The shared helper now preserves the spatial partition, tab order, active tabs
  and neighboring widths before rebuilding the split. Nested vertical partitions
  are preserved as well as horizontal rows.
- Cross-container center drops now use the pointer's anchor instead of the last
  registered dock in the receiving workspace.
- A single-file IDE column can move left/right at the three-column cap without
  creating a fourth column. Drops onto empty columns reuse those columns.
- Empty header space inserts tabs, and rejected targets show no split preview.
  Cancellation returns the preview to its owning source before groups can close.

Validation used actual widget rectangles and QSplitter widget order, not just
successful return values. The shared matrix performs 72 repeated physical side
placements across left-to-right and right-to-left layouts, plus tab-companion,
center-transfer, nested-partition and neighboring-width checks.

Results: 47 shared docking tests and 25 IDE tests passed from clean committed
snapshots. The final empty-column regression passed separately. Eighty application
regressions passed across MainWindow, Documents, Git tabs and IDE. Native Cocoa
runs passed all six IDE-layout and five shared-placement tests (the final
empty-column case was checked offscreen). Ruff and whitespace checks passed.
Native Windows/Linux interaction remains unverified.

## Release validation follow-up

The application opts into shared header menu publication on every desktop.
The Logistics navigation menu remains alongside feature-owned actions, including
plain destinations and empty IDE/Git workspaces. Browser views own conventional
menus and obtain eligible selection contributions from the existing context-menu
builder. Bulk Rename shares one menu definition between hosted and standalone
windows; its bottom action area groups secondary commands beside Rename.

Git hunk cards publish their measured height-for-width as a fixed card height,
so native layouts reserve exactly the space the card occupies and keep the
10-pixel inter-card gap. Focused checks cover 10 hunk layout cases and nine File
Tools cases; the browser fixture joins its workers before deleting its window.

Windows headless validation exposed a minimum-width constraint in Bulk Rename's
combined preset/action row. Presets now occupy a separate row, allowing the main
actions to fit a 680-pixel window with larger font metrics. The existing narrow
layout regression continues to verify rule reflow, retained values and readable
filename columns; release platform checks validate the change on each OS.

Fix commits: commonUtils `c043426`, `ea31bcc`; Logistics `9ade07e`, `b4a6700`.
Concurrent gesture-observer, menu, Markdown and navigation edits remained outside
these commits.
