# Mobile host code

`Python/mobile/` owns Toga application state and composition. `mobile_build/`
owns preparation, deployment and native validation. Paths below are relative to
`Python/mobile/` unless qualified.

| To change | Start with |
| --- | --- |
| Host or feature wiring | [Owners](#owners), [host capabilities](#composition-and-explicit-host-capabilities) |
| Folder data or mutations | [Discovery](#workspaces-folder-discovery), [listing](#folder-listing-ownership), [operations](#file-operation-ownership) |
| Text creation, Open or Save As | [Picker lifecycle](#opensave-as-lifecycle) |
| Reader open, page change or Close | [Provider assembly](#provider-presentation-assembly), [publication](#reader-publication-boundary), [session transitions](#session-transition-decisions) |
| Startup, settings or retirement | [Startup](#native-startup-progress), [Settings](#settings-implementation-owners), [shutdown](#application-shutdown-and-disposable-resources) |
| Native pane placement or an input gesture | [Workspace navigation](mobile-workspace-navigation.md) |
| Stage or profile a change | [Mobile preparation](../build-release/mobile-preparation.md), [performance checks](../testing/mobile-performance.md) |

## Owners

| State or UI | Owner |
| --- | --- |
| Startup, lazy services, feature presentation ports | `app.py`, `composition/{assembly,presentation}.py` |
| Session identity, generation, windows and scenes | `workspace.py`, `window_owners.py`, `window_scenes.py` |
| Home and Documents | `home.py`, `documents_hub.py`, `hub_controls.py`; summaries and reopen in `hub_ui.py` |
| Destination routes, panes and retained drawers | `routes.py`, `workspace_navigation.py`, `adaptive_workspace.py`, `file_drawer.py` |
| Managed text and checkpoints | `documents.py`, `managed_documents.py`; controls under `Python/features/text_editor/mobile/` |
| Library and provider sessions | `reader_sessions.py`, `private_sessions.py`; capability facade in `reader_host.py` |
| Chapter drawers, edge layout, memory and progress | `reading/{chapter_drawer,reader_edges,reader_memory,reader_progress}.py` |
| Screen lock and reader privacy | `screen_privacy.py`; source data rules in [document storage](document-storage.md#privacy-and-lifetime) |
| Chat, catalogue and Notes | [LM](../../features/lm/development/development.md#mobile-ownership), [Books & Comics](../../features/books/development/development.md#find-the-mobile-books--comics-panel), [Notes Library](../../features/notes_library/development/development.md#mobile-browsing-and-document-lifecycle) |

Formats own decoding and document-specific controls. Rclone owns cloud,
collections and encrypted-copy adapters. commonUtils owns shared toolkit
mechanisms, including reader layout metrics. Secondary scenes share the command
registry and application services, with independent navigation and document state.

### Trace a document or cancellation

- **Reopen:** `document_sources.reopen_file` owns the loading panel and resolves the current source. `PrivateSessions.open` checks capacity, captures navigation/workspace and credential identity, then reads. Admission precedes view adoption, progress restoration and history updates. Stale or failed opens retire their temporary resources and restore the previous owner.
- **List:** `FolderListing.begin` retires the previous request. `capture` freezes provider and location. `read` checks `accepts` around worker I/O. To change listing cancellation, run the following from the repository root. Expect an old read or error to leave the newer rows intact and unrelated credential changes to preserve ordinary Local reads.

  ```sh
  python3 dev.py test mobile --exact-file mobile_build/tests/storage/test_folder_listing.py
  ```

- **Cancel a transfer:** the transfer controller owns its event and review close callback. Host Cancel also reaches independent file/cloud work. Review approval remains tied to its captured session.
- **Replace a host:** preserve and revalidate first, claim the successor, then retire old callbacks. See [host retirement](#application-shutdown-and-disposable-resources).

## Composition and explicit host capabilities

`composed_workflow` lazily installs only declared `METHODS` and `FIELDS`.
Duplicate claims fail before registration. `Python/services/workflow_host.py`
defines read-only `HostService`, writable `HostAttribute` and record-backed
`StateAttribute`. Pass feature adapters explicit capabilities through
`composition.presentation` and keep their imports independent of the mobile host.
For example, rclone gets folder-route and loading-panel callbacks and Text Editor
gets font and folder actions. Pinned locations use a `LocationHost`; a remote pin
lookup admits navigation and errors only for the captured client, generation and
live host.

If revealing Files returns `False`, stop the pinned-folder open. After
an await, validate the selected browser and navigation generation as well as
the connection. An individual open shields the shared startup credential
restore from cancellation. Encrypted folders are ineligible for persistent
pins. Exercise these boundaries in `test_locations.py`.

## Workspaces folder discovery

`FolderController.discovery` owns the refresh task, cache, credential stamp
and invalidation epoch. It snapshots mappings, remote names, crypt locations and
account identities on the UI loop. `folder_hub.discover_folder_choices` scans
local names from the detached snapshot, retaining grouping and copy precedence.
Discovery reads published metadata, while credential loading owns native crypt
discovery. Browsing still checks access when invoked.

Concurrent requests share one scan and coalesce another when needed. Locking
clears cached private names immediately. Result and error publication require the
current host, epoch and credential generation. A request made after invalidation
survives the old worker's retirement. Native views can display a matching cached
snapshot while refreshing. Run `python3 dev.py test mobile 'test_folder_*.py'` for
snapshot isolation, stale results, retry and retained tree coverage.

## Workspaces refresh

Workspaces refreshes on entry and credential/transfer changes. Failed discovery
offers **Try again**. `WorkspacesScreen` owns the root and source tabs,
`FolderHubUI` owns their workflows, and `FolderTreeView` reconciles each retained
source's rows, guides and menus. Update only affected controls. Retire removed
menus, resolve commands at invocation, and preserve unrelated Local rows when
remote metadata changes. The focused `test_folder_tree_view.py` and
`test_folder_navigation_performance.py` cover row identity and bounded refresh
work. See the [shared locked/unlocked artwork](ui-architecture.md#shared-lockedunlocked-folder-artwork).

## Folder listing ownership

Each main browser and workspace drawer owns a separate `FolderListing` and
cancellation event. Discard stale errors as well as results after a newer
request, location change, host/browser retirement, or private lock or credential
replacement. Preserve ordinary listings across unrelated credential refresh.
`files_ui.py` resolves the provider and owns labels, sort, search and failed
navigation recovery. Drawers read through a captured `ResourceSelection`.
Listing remains available during transfers. Picker and credential setup have
separate owners.

Keep `RecycledFileList` in a bounded native viewport. Android uses the app's
Java ListView adapter; iOS uses reusable UITableView cells. Rows bind from a
complete filtered snapshot, validating the entry and render epoch before
activation. Rebind the palette, image and accessibility on redisplay, including
unlock of a retained window. Only visible cells request optional thumbnails,
with bounded work and caching. Ordinary Local and LocalCrypt lists browse names
and generic icons without thumbnail reads. Tiles use their own scroll surface.

## File operation ownership

`FileOperations` receives a captured `FileOperationRequest` containing the
operation, source provider/path and target data. Forms and destructive prompts
stay in `files_ui.py`. Resolve encrypted destinations on the worker with captured
credentials and generation checks. The composition adapter enforces the busy,
dirty-reader and transfer guards. Keep the busy guard until the worker retires,
including cancellation; the shared Cancel reaches each workflow's own event.

Move uses the shared verified, non-overwriting primitive. Keep a source until
verification succeeds. Use copy/encryption and verification progress, and reject
late updates from a retired presentation. A background/lock cancellation leaves
a stopped message for explicit retry; a late committed move is reported as
completed. The counted `AwakeLease` retains native screen-on state until the
last transfer/player releases it. It controls idle sleep. Native writes can
report physical bytes with indeterminate progress until measured verification.

`document_mutations.py` owns editable-document identity handoff. For checks use
`test_file_operations.py`, `test_files_ui.py` and the [native file-transfer
probe setup](../build-release/mobile-device-deployment.md). Check overwrite
refusal, captured Delete identity, stale status and cancellation cleanup.

## Open/Save As lifecycle

`app.editor_picker()` lazily retains one `EditorPicker` per host. It owns the
origin, provider selection, pending bytes, privacy gate and current operation.
`document_destination_form` attaches named controls to that owner.
Listing, resolution, writes and verification run on workers with captured
values. Admission checks host, operation/epoch, navigation, credentials and
source privacy. Clear pending work on lock or retirement, and keep the busy
guard until cancellation settles.

- **New:** `show_document_creation` shares one naming and browsing route. Choose ordinary or unlocked LocalCrypt storage, including mapped copies. Use the non-overwriting operation to publish empty text/Markdown and reopen through the provider. Completion removes the picker route. A failed open preserves the form; Cancel restores the origin.
- **Open:** validate the captured selection and provider capabilities before opening. New folder enters the created location only while that picker is still current.
- **Save As:** `destination_names.save_filename` validates a single child name. A basename inherits a supported suffix or defaults to `.txt`; invalid explicit suffixes are rejected. Confirm replacement and recheck revision. Verify the reopened bytes before source handoff through `app.finish_save_as_source`. Keep the draft on reopen failure. Cancel and native dismissal return to the captured source, including new drafts. Cancellation can arrive after successful publication.
- **Move:** `show_destination` uses the same browser. The operation keeps captured source identity and separate destination selection. Direct remote targets are excluded from text creation; encrypted creation uses `encrypted_copies()`.

See [private export consent and draft lifetime](document-storage.md#privacy-and-lifetime).
Run `test_editor_picker.py`, `test_destination_workflows.py` and
`test_document_creation.py`. Native Save As and creation probes also exercise
the keyboard, real returned bytes, replacement/reopen failures and LocalCrypt.

Keep publication in `services.documents.destinations`. A detached worker snapshot
holds operation identity even when the route is replaced. New picker entry or
clear invalidates that record, including notebook serialization callbacks. The
same retained form reflows between compact steps and adjacent naming/location
panes. Native keyboard ownership is described in the [navigation guide](mobile-workspace-navigation.md#storage-selector-keyboard-lifetime).

## Provider presentation assembly

`ProviderDocumentSession` owns the reader and metadata draft. `provider_opening`
prepares the reader and initial Markdown off the UI loop, with source fallback
after render failure. `ProviderView` builds unpublished controls.
`provider_presentation` builds chrome from explicit host, controller and view
inputs. Check cancellation and view admission before adoption. Dispose rejected
controls without closing the supplying owner's reader. After adoption the
session owns disposal, including retries for failed cleanup; retain session
ownership if later presentation work raises. Release busy state and temporary
remote sources through their owning workflow. Reader teardown attempts each
cleanup step and clears its password. See [provider reader workflow](document-storage.md#trace-a-mobile-provider-reader).

Managed Markdown instead uses `ManagedDocumentWorkflows.show_preview` for
checkpoint, route, saved scroll and Edit policy and `preview.prepare_managed_preview`
for controls. The retained `TextEditorView` owns their lifetime. Keep source,
preview, search and speech state per editor.

### Native source editor and live Markdown

The [Text Editor mobile owner](../../features/text_editor/development/development.md#mobile-editor)
uses commonUtils CodeInput for source and the offline renderer for formatted
content. Markdown live preview defaults on and uses the session's
`markdown_split` flag; it places source beside preview at 720 usable units.
Keep the full-page preview and source fallback. For Android 12+,
`native/android_markdown_font.py` supplies eligible native glyph tables to marked
WebViews via a unique local font URL with RAM-backed no-store responses. Retire
the URL with its view. Older Android, inaccessible faces and font buffers above
32 MiB use CSS fallback. Keeping font bytes outside HTML preserves the existing
private-page bound. Check `test_markdown_font.py` for routing and retirement.
Native editor checks should exercise IME, syntax coloring, selection and Undo.

## Reader publication boundary

`ReadingPublication` captures outgoing motion, admits a prepared surface,
retires replaced controls, then updates footer and chrome. `reading.sources`
captures the live host and library reader/epoch or provider reader/workspace
token. Use `preparing(direction)` around construction to release animation
snapshots on failure. `mount` checks validity again and disposes rejected
unmounted surfaces. A construction failure preserves the displayed page.
Exceptions during accepted mount clean up animation; arbitrary host mutations
may already have run.

`ProviderUI._show_crypt_content` prepares the target spread or EPUB page before
mount. Commit PDF pixels and link geometry together after admission. Library
`ReaderUI.display_book_page` mounts before progress writes and captures the
reader, epoch and chapter in callbacks. `test_reading_publication.py` covers
retirement during placement and view-preparation failure.

`PageFooter` shares 48-point touch controls and release-only seeking across EPUB,
comics and PDF. EPUB seeks chapters, while the caption can show intra-chapter
progress. PDF's vertical rail shares validation and failed-seek handling; manga
reverses both mapping and track fill. Native bars mount the reader Close control
on main routes and Back on tools routes. File titles and storage subtitles use the
current container. For vertical bars and reader headers, see [system occlusion
clearance](mobile-workspace-navigation.md#system-occlusion-clearance).

Use commonUtils' `READER_LAYOUT` for shared track, thumb and touch geometry.
`reader_edges` consumes reported Android corners; iOS uses measured safe areas
and remaining Home-indicator clearance. Preserve canvas space separately from
touch targets. Native video receives transient layout metrics through its
bridge. `document_storage_tools --probe viewer-layout` covers viewer controls
across formats and rotation on disposable profiles. Its iOS family matrix uses
the runner's pinned simulator helper.

Transfer status actions reuse native reader chrome. Progress changes update
the label in place; action availability changes reflow the group. Completion
uses an epoch guard before hiding the notice; stopped work stays visible.
Back from details preserves the transfer and the current destination.

## Session transition decisions

`SessionTransitions.prepare` captures the session key, provider and workspace
token. `commit` rejects stale or cancelled decisions.
Require `CloseResult.committed` before removal or navigation. Dirty-dialog
answers revalidate the workspace token and active host before Save/Discard;
busy exits await owned work. `session_workflows.adapters` retains each source's
checkpoint and cleanup. Native modal prompts use `services.documents.authoring.document_dialogs`.
Retire a closed session's presentations across all tabs and Documents detail.
Explicit reader exit also restores its retained origin and refreshes open/recent
summaries; a hidden session can be removed without navigating to it.
`test_session_transitions.py`, `test_reader_lifecycle.py` and
`test_document_navigation.py` cover these paths.

## Application shutdown and disposable resources

`HostLifecycle` checks notebooks, transfers and private readers, then
checkpoints through session transitions. A veto keeps the host usable for retry.
Replacement flushes mounted native input, checkpoints reader progress and
revalidates private receipts and notebook state before marking sessions terminal
and claiming the successor. Startup revalidates that claim before publishing
loaded models. Cleanup after the claim can be retried by resource identity;
the successor retains ownership. Android Activity replacement retires old IME,
navigation, Back and resize callbacks before workspace reuse.

Accepted exit and replacement invalidate owned presentations and tasks. Only
ordinary accepted exit disposes the process-shared external comics display.
An OS-disconnected secondary scene attempts its checkpoint once, logs sanitized
failure and retires even on veto; registry cleanup compares host identity.
`abort_startup` retires partial state without checkpointing.
`services.worker_retirement.drain_worker` waits through repeated caller
cancellation and retrieves worker errors. The workflow owns signalling, admission
and the original cancellation. See [incoming files](../build-release/mobile-preparation.md#incoming-files-and-inbox)
for receiver handoff and publication locking. Check `test_application_lifecycle.py`,
`test_startup_models.py` and `test_window_owners.py`.

## Sleep, memory trimming and visible library readers

`ScreenPrivacy.resume_reader` schedules one guarded recovery for the visible
provider or library reader. Preserve the control mode, page/passage and route.
Revalidate visibility, privacy and workspace identity before recovery. Archive
password prompts still apply. A late Android trim can arrive after resume;
request the same recovery after trimming and defer it while locked or inactive.
`test_reader_sessions.py` covers duplicate wake, stale tasks and late trim.
The disposable `reader_resume_probe.py` exercises Android Activity and memory
callbacks; physical Boox behavior requires its own evidence.

## Native startup progress

`StartupScreen` and `app._startup_steps` report eight real phases from private
storage through workspace opening, yielding a draw turn before each. Labels
exclude private names and paths. With restoration enabled, reopen the active
ordinary document before reveal. Otherwise show Home. Android holds a native
loading snapshot until measured workspace bounds stabilize and suppresses
premature taps and accessibility. Wait for `on_running` to interact in native
probes. Startup failure logs phase and error type, shows a generic recovery page
and withholds readiness. Secondary scene failure releases its own window and
writers.

Cloud restoration starts after reveal and shares one task with later callers.
Controls and remote browsers initialize on demand. Local reads can proceed while
credentials restore; cloud reopens wait and validate connection identity.
Terminal retirement cancels the independent restore; ordinary Cancel keeps it
available to other callers. Run `test_startup_progress.py` and
`test_background_credential_refresh.py`.

## Startup and document responsiveness

Construct Settings on demand and scan the Libraries collection when shown.
Ordinary file taps open directly and validate the visible listing before
publication. Prepare initial provider Markdown on a worker. Android layout
callbacks skip reflow when bounds, insets, navigation mode, destination and body
identity match. For measured changes see [mobile performance](../testing/mobile-performance.md).

`workspace.py` bounds restoration reads to 64 KiB plus one byte and preserves
an invalid manifest and its save veto. Skip redundant checkpoints only when
ordinary session state, on-disk revision and bounded persisted bytes match.
Managed-text recovery also checks content, encoding, original bytes and
recovery revision. Changed or missing data forces publication; linked paths are
rejected. A failed checkpoint keeps navigation blocked for retry.

`layout_participants` owns weak reflow subscriptions for hubs, Settings,
documentation, Notes and text. Stable ordering applies adaptive layout before
the final coalesced reader wakeup. Retire subscriptions by owned identity so
a replaced view cannot unregister its successor. Scene activation can arrive
before startup completes; record it immediately and call privacy/focus
handlers once their owner exists.

## Settings implementation owners

`settings/categories.py` declares lazy factories, icons and gates;
`settings/navigation.py` retains per-window category pages. Use named panels,
`settings/forms.py` for shared controls and the [panel recipe](ui-architecture.md#add-or-change-a-settings-panel).
Saving reads constructed controls and preserves values for unopened categories.
See [INI compatibility and defaults](configuration-and-data.md#mobile-preference-ownership).
Per-format Markdown, text and EPUB sizes seed from legacy `font_size`; their
12–32 range is shared by Settings and pinch. Update mounted surfaces in place.
Markdown and EPUB justification use separate validated Booleans with false
defaults. Refresh the shared CSS alignment variable and reflow without reloading.
Keep EPUB anchored and leave native source alignment to its control.
The iOS legacy visibility switch previews through a session override; Save
persists it and Reload discards it. Filter logical names and credential labels
in presentation and reset a hidden credential selection to All.

Credential import uses the system picker, bounded ZIP metadata, a password
prompt when required and explicit session/persistent choice. Password retries
reuse the pending archive; route retirement clears it. Native publication checks
the captured connection. `test_cloud_import_ui.py` covers these paths.

### Mobile feature selection

`Python/services/mobile_features.py` maps shipped groups and document kinds.
`Mobile.disabled_features` defaults to `[]`. Books & Comics preserve both
portable IDs and toggle atomically. Secondary scenes share the primary feature
owner through `feature_settings.py`. Refuse disabling a group with open
documents or active chat/storage work. Admission, creation and Settings use the
same catalogue, with provider names rechecked after decoding. Local document
storage and Help's wiki remain available independently. Tests can enable a
feature through `app.set_feature_enabled(name, True, refresh=False)` before
construction. Run `test_mobile_features.py` or the native `--probe features`.

## App reset boundary

`app_reset.py` owns reset. Android targets its own application data. iOS records
a durable schema-only request and handles it before migration. Require ERASE and
an idle single window. Delete the two Logistics Keychain service namespaces
before app files/defaults. Keep the retry marker until all steps finish; refuse
linked roots and unlink contained symlinks without following them. Suppress
checkpoints and new windows until process restart. Collection volumes outside
the app container are outside reset erasure. The iOS privacy manifest declares
CA92.1 for app-only defaults.

Collection operations stay in `storage_ui.py` and `storage_location.py`.
Stage and verify both trees and source revisions before committing a new
location. Protect the active location from wipe; empty setup requires an empty
destination. Android API 24–29 exposes mounted app-owned directories with
uninstall/clear-data lifetime. API 30+ uses mounted volumes and All files access.
See [collection recovery](configuration-and-data.md#android-collection-location-recovery).

## Packaging and verification

Add a new module to its owning `mobile_sources.json` alongside the import.
`mobile_build/tools.py` validates manifest closure and builds the payload.
Edit source in its owner. Follow the [host validation commands](../build-release/mobile-launchers.md#host-validation)
for focused tests and staged startup. Use owned disposable devices for native
Back, touch targets, rendering and encrypted I/O; keep reports in ignored
evidence directories. The [navigation checks](mobile-workspace-navigation.md#native-navigation-validation)
describe native scenarios.
