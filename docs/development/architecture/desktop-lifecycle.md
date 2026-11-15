# Desktop startup, navigation and shutdown

Follow `Python/launch.py` into `desktop/main_window.py:MainWindow` to
trace startup and window ownership. For a particular panel, use the
[screen map](ui-architecture.md). For save and close decisions in a document
window, see [document sessions](document-storage.md#independent-text-documents).

## Startup and refresh

Platform launchers read `launch_config.ini`, synchronize Python and invoke
`Python/launch.py`. Create Qt before feature initialization so startup can display
errors. Start the index participant, apply theme/preferences, initialize enabled
features, construct MainWindow and enter the event loop. The [registry](features.md)
registers types before hooks and runs hard dependencies first.

Validate page IDs before calling factories. Refresh a page when selected.
Resolve Workspaces declarations on the GUI thread, then discover providers and
action availability in workers. Mount controls on the GUI thread only after
checking the current selection and credential. Explicit refresh rereads sources.

## Desktop launch and destination projection

`desktop.navigation.catalog.LaunchCatalog` projects core and enabled contributions
to landing cards, rail targets and document choosers. Full hub shows the rail.
File Browser, Git (`git.workspace`) and IDE (`ide.workspace`) reuse their pages in
the per-window rail-free mode. Disabling the active standalone feature returns
to the chooser. Retain `DestinationRail.tools_menu` and the Misc `tools` glyph
for future nested destinations.

The rail and chooser share registered document launchers, including core
Markdown. The Documents popup groups windows by `document_editor_id`; detached
windows offer Bring back. Empty document workspaces and the `+` tab reuse
`DocumentChooser`. Its `creation_scope` routes Open/New to the requesting
workspace. Cancel keeps the chooser. A successful open reveals the retained
document. The floating Settings control shares rail menu actions.

The active workspace supplies `workspace_menu_document` to commonUtils' menu
router. Test visible menu updates when switching docked tabs on macOS. Detached
docks are regular native windows with cooperative close. Workflow tabs and
metadata dialogs retain their own owners. Main-window F11 belongs to
`desktop.fullscreen.WindowFullscreen`.

Check chooser changes with `python3 dev.py test desktop test_document_launchers.py`
and `python3 dev.py test desktop test_landing_appearance.py`. Expect enabled
cards, retained Open/New routing and settled row geometry before first paint,
including compact widths and delayed font changes. Keep layout settling scoped
to the chooser so it cannot dispatch unrelated startup events.

## Long-running workflows and safe closing

Capture validated inputs and prompt on the GUI thread. Use commonUtils
`OperationProgress` or `Operation` for worker callbacks. Route close/Escape to
cancellation and retain the owner until the worker finishes. Browser workers
also need `stop()` and `idle`. Feature disablement removes future contributions
while retained jobs finish. [Shared workflow recipes](../../../Python/commonUtils/docs/development/reference/ui/operation_progress.md)

Choose transaction boundaries with the feature owner. ZIP creation cancels
between chunks and discards staged output. Comic batches finish and verify the
current archive, retain completed items and report per-item failures.

## Desktop notifications

`desktop.notifications.notification_service()` retains the QApplication's
bounded NotificationCenter. Publish a stable ID, source, title, message and
outcome. Acknowledgement clears unread state. Details actions that refer to a
widget check that it is still live. Toast/native delivery is optional and
separate from retained task results. Keep password and destructive decisions in
owned dialogs and report cancellation as its own outcome.

## Startup failures

MainWindow rolls back failed construction or wiring and waits for retained
workers. After construction, the launcher clears pending update handoff and
retires the window before stopping indexing. Interactive close checks save vetoes
before cancellation. Check `test_main_window_navigation.py` and `test_launch.py`.
Keep the macOS launcher compatible with system Bash 3.2.

## Application update handoff

`services.updates` owns channels, protected roots and verified staging.
`desktop.updater.UpdateController` checks on a worker; the landing page offers
the update. A close veto aborts handoff. After Qt exits and indexing stops, the
copied commonUtils helper revalidates, applies and restarts. Failed preparation
reports any staging cleanup failure. The helper retains recovery staging after
application failure. Failed rollback needs manual recovery before launch.
Startup consumes valid failure receipts and preserves malformed receipts.
