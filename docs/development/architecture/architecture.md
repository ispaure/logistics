# Application architecture

### Find a code or UI owner

- [Repository and code map](code-map.md)
- [Screen and panel ownership](ui-architecture.md)
- [File browser development](file-browser.md)
- [Mobile host runtime](mobile-runtime.md)
- [Mobile workspaces and navigation](mobile-workspace-navigation.md)
- [Mobile accent controls](mobile-accent.md)
- [iOS Shortcut value widgets](shortcut-widgets.md)

### Change a shared contract

- [Document storage sessions](document-storage.md)
- [Reader progress and history](reader-state.md)
- [Configuration and compatibility](configuration-and-data.md)
- [Access and privacy](access-privacy.md)
- [Audio and capture privacy](audio-playback.md)
- [Logistics host services](services.md)

### Add or extend a feature

- [Feature organization and lifecycle](features.md)
- [Feature registry and infrastructure](feature-infrastructure.md)
- [Application extension points](extension-points.md)
- [commonUtils integration](commonutils-integration.md)
- [Optional external feature integration](optional-integration.md)

[Developer index](../development.md)

## Shell, features and services

Desktop uses Qt/PySide6. Mobile uses Toga and native controls, with an explicit
source manifest. The shell owns navigation and retained views. Features own
domain behavior and their own views. Logistics services own app policy.
commonUtils supplies reusable mechanisms. `logistics_build/` adapts the
standalone Build Deployment Manager to Logistics tests and releases.

A host composes a component. A provider supplies storage or service access.
A session retains state and resources until its owner retires them.

| Trace | Start here |
| --- | --- |
| Settings → Appearance | [Screen map](ui-architecture.md#find-a-screen-by-its-visible-name) |
| Encrypted or remote document open | [Provider to reader](document-storage.md#trace-a-mobile-provider-reader) |
| Desktop startup or rollback | `Python/launch.py`, then `desktop/main_window.py` |
| Mobile startup or packaging | [Mobile preparation](../build-release/mobile-preparation.md) |

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

## Long-running workflows and safe closing

Capture validated inputs and prompt on the GUI thread. Use commonUtils
`OperationProgress` or `Operation` for worker callbacks. Route close/Escape to
cancellation and retain the owner until the worker finishes. Browser workers
also need `stop()` and `idle`. Feature disablement removes future contributions
while retained jobs finish. [Shared workflow recipes](https://github.com/ispaure/commonUtils/blob/main/ui/operation_progress.md)

Choose transaction boundaries with the feature owner. ZIP creation cancels
between chunks and discards staged output. Comic batches finish and verify the
current archive, retain completed items and report per-item failures.

## Independent text documents

The QApplication-owned EditorService retains one window per document, even
after the originating browser closes. Open reuses the existing buffer.
`DocumentsPage` owns dock tabs. `request_document_close()` returns
`CloseOutcome.ACCEPTED`, `VETOED` or `PENDING` so the host can distinguish Cancel
from asynchronous retirement. The owner handles prompts and publishes `idle`.
Plain windows retain native close vetoes, and legacy `prepare_close()` can defer
closure.

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

## Shared controls and desktop notifications

Use commonUtils outlines for Markdown headings, EPUB chapters and bookmarks.
The entry target remains opaque to the widget. Use shared `entry_views` for
selection and sorting. Keep the archive-member and filesystem-index models with
their respective owners. Reuse `atomic_write_bytes` for verified publication.
The caller validates format, encoding, symlink policy and schema.

`desktop.notifications.notification_service()` retains the QApplication's
bounded NotificationCenter. Publish a stable ID, source, title, message and
outcome. Acknowledgement clears unread state. Details actions that refer to a
widget check that it is still live. Toast/native delivery is optional and
separate from retained task results. Keep password and destructive decisions in
owned dialogs and report cancellation as its own outcome.

## Multiple application instances and shared indexing

Each app process participates in the same durable index queue without a launch
lock. The OS coordinator lock elects a runner and the writer lock serializes
mutations. A browser drops its own subscription on close. App exit drains the
worker, releasing SQLite and locks. A later launch can resume unfinished index
requests. [Browser index scope](file-browser.md#directory-index-admission-and-foreground-demand)

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

## Portable owner policy

`Scripts/architecture.json` declares portable modules and recursive packages.
`python3 dev.py architecture` checks direct and literal deferred imports.
`test_portable_imports.py` imports selected owners in fresh interpreters with Qt,
Toga, host packages and `commonUtils.ui` blocked. Review dependency additions at
the narrowest owner. Presentation-only exceptions, such as LM's desktop Git
preview, apply at their declared call sites.

See the [document storage guard](document-storage.md#enforced-architecture-contract)
for forbidden raw I/O and scoped exceptions. Use commonUtils for reusable
[presentation and persistence](commonutils-integration.md).
