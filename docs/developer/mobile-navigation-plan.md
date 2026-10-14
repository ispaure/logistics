# Mobile native navigation and document workspace plan

## Current decisions and implementation status

The user updated the destination order after the initial shell: **Home, Files,
Documents, Settings**. Home is a landing page with a house icon before Files on
both mobile platforms. This supersedes references to three destinations in the
original milestone text below. Desktop also has a first-position Home toolbar
action returning to its landing page.

Milestone 0 foundation is committed; actual native destination wiring is committed
with native Back/routes and independently editable text documents. Adaptive
Documents panes and recovery are implemented. The current checkpoint adds library
sessions and brings forward part of milestone 4: Settings connection setup,
visible remote action feedback and one-time folder pulls to local storage.
Full private-session integration, unified Files refinement, repeatable sync,
reader visual refinement and independent windows remain unfinished.

## Remaining phase numbering

The continuation uses Phase 1 for milestone 3 (mixed/private sessions), Phase 2
for milestone 4 (Files/connections and repeatable pulls), Phase 3 for milestone 5
(reader/editor presentation), and Phase 4 for milestone 6 (independent windows).
Each phase uses numbered Part commits. Phase 1 Part 1 introduces four bounded
provider-session owners, independent private drafts/metadata, duplicate activation,
Open documents access, all-owner credential guards and exclusion from recovery.
Phase 1 Part 2 adds a native mixed/private workspace case; all 19 native cases
pass on both the iOS 27.1 Duo simulator and Android 15 emulator. Resource-pressure
hooks and later phase exit gates remain pending.

## Phase 0 submission boundary and numbered checkpoints

Phase 0 is the first end-to-end deliverable described below (milestones 0–2),
with the later reader/Files improvements already present in checkpoint `8de00ed`.
The resume sequence uses numbered commit subjects; earlier history is preserved:

| Checkpoint | Result |
| --- | --- |
| Baseline `8de00ed` | Native Home/Files/Documents/Settings, routes, recovery, adaptive text panes, library sessions and explicit one-time local folder pulls |
| Phase 0 Part 1 `165a4f0` | Save, Keep draft, Discard and Cancel on dirty text Close; conflict-safe discard and owner-targeted close |
| Phase 0 Part 2 `261c68e` | Per-document Edit/Preview continuity and preview callback ownership |
| Phase 0 Part 3 `ea03d85` | Unavailable restored resources offer Retry/Remove without displaying another document |
| Phase 0 Part 4 `8619493` | Native evidence, submission notes and validation status |
| Phase 0 Part 5 `55a9310` | Material-themed Android bars keep inactive destinations visible |
| Phase 0 Part 6 | Final contrast checks, normal-launch verification and release submission |

The Phase 0 implementation passed both final native suites and is ready for
an alpha submission. Existing lifecycle evidence covers two ordinary drafts
through Apple rotation/background/process restart and Android live resizing,
Activity recreation and process restart. The final submission reruns both native
suites against the current sources. Device-specific manual checks remain release
limits: the retained iOS minimum, physical document-provider permissions, real
fold gestures, accessibility combinations and physical BOOX/E Ink behavior have
not all been verified. Independent windows are not part of Phase 0.

Milestone 3 private-session expansion, milestone 4 repeatable sync and the unified
Files experience, milestone 5 reader/visual refinement, and milestone 6 independent
windows remain future phases. This submission does not claim those are complete.

Status: proposed implementation plan, agreed design direction. Prepared October
13, 2026. Milestones below describe future work, not shipped behavior.

Build Logistics mobile around **Files, Documents and Settings**, with a shared
Python model for navigation, open documents and recovery. Use native platform
containers for presentation: Apple navigation on iPhone, iPhone Duo and iPad;
Material navigation on Android phones, tablets and foldables. Begin with native
navigation and two independently editable text documents before expanding the
workspace to readers and storage workflows.

## Product decisions

- **Files** owns locations, pinned folders and folder browsing. The folder hub is
  the root of Files, not another primary destination. Opening a supported file
  activates it in Documents; returning to Files restores the browsing context.
- **Documents** owns open text, Markdown, EPUB and comic sessions. Open items are
  distinct from saved documents, the reading library and recent items. Closing
  an open item does not delete its file or remove it from the library.
- **Settings** owns appearance, preferences, connections and credential
  management. Existing LM conversations remain reachable through Documents,
  with server configuration in Settings. Everyday chat does not belong only in
  Settings.
- Destination switching preserves work. Folder navigation, open-document
  switching and window management are separate concepts.
- Phone layouts show one main pane. Larger windows can show an open-item list
  or file list beside the active document. Reading can expand to full content.
  Desktop-like floating docks and arbitrary pane splitting are later work.
- Use the platform's labels, icons, selection, accessibility and interaction
  behavior. Share destination identities and workflows across platforms without
  forcing their bars into identical positions.

## Current implementation and constraints

These are the starting conditions to preserve or replace deliberately:

| Area | Source and current condition | Consequence |
| --- | --- | --- |
| Mobile shell | `Python/logisticsmobile/app.py` builds ordinary Home/Documents/Settings buttons and swaps a single body view | Replace the navigation host; do not merely restyle the buttons |
| Text documents | `documents.py` stores UUID identities, encoding, original bytes, drafts and conflict-aware saves; `app.py` holds one `current` document and one editor | Reuse storage contracts, introduce multiple independently owned sessions |
| Books and comics | `library.py`, `library_ui.py` and `reading.py` provide private imports, progress, bookmarks and archive access; UI holds one active reader | Add reader sessions without duplicating archives or changing format support |
| Private readers | `localcrypt_ui.py` holds one private reader and refuses to clear unsaved edits; private content and passwords stay out of ordinary recovery | Preserve the privacy boundary when making sessions switchable |
| Storage | `files_ui.py`, `file_resources.py`, `cloud_ui.py` and shared providers implement browsing and capability-aware operations | Reorganize their entry points without replacing provider transactions |
| Python and native host | `Mobile/pyproject.toml` pins Toga 0.5.7 and Briefcase 0.4.5; iOS minimum is 15.0 | Evaluate upgrades separately; modern APIs need availability checks |
| iOS tabs | The generated pinned backend's `OptionContainer` wraps `UITabBarController` | A native tab foundation exists; new sidebar/Duo behavior still needs proof |
| iOS windows | The pinned iOS backend rejects secondary windows and binds its scene delegate to the current main window | Independent iPad windows require backend lifecycle work |
| Android tabs | The generated pinned backend wraps Material `BottomNavigationView` | Use native bottom navigation first; adaptive rails need additional integration |
| Android dependencies | The backend requires Material; the app's explicit Gradle dependency list does not declare it | Audit the resolved dependencies and declare the verified compatible requirement |
| Android lifecycle | The generated activity handles orientation, screen size, screen layout and hidden-keyboard changes itself | Test both configuration callbacks and genuine recreation/process restoration |
| Packaging | `Mobile/tools.py` explicitly lists allowed app modules | Add new modules, icons and native build resources to staging and its tests |

Generated build files are evidence of backend behavior, not source files to patch.
Keep reproducible changes in tracked application, configuration and build tooling.
The existing [mobile implementation guide](mobile-preparation.md) and
[mobile user guide](../../Python/logisticsmobile/user_docs/README.md) remain the
references for implemented behavior and limitations.

## Architecture and ownership

### Shared Python model

Introduce a small application coordinator with no Toga, UIKit, Android or Qt
imports. It owns destination state, document sessions, workflow commands and
restoration. Existing document stores, resource providers, archive readers and
the native rclone bridge retain responsibility for bytes and transactions.

Use the following ownership boundaries:

| Component | Responsibility |
| --- | --- |
| Navigation state | Selected destination, Files location/history, Documents selection and route within each destination |
| Session registry | Open order, resource identity, document kind, active session per workspace, dirty/conflict/locked status |
| Document controller | Existing store or provider operations for open, checkpoint, save, export, close and disposal |
| View state | Cursor/selection, editor scroll, preview mode, reader position and relevant selection; no native widget references |
| Operation coordinator | Operation identity, originating session, cancellation, revision/generation validation and result routing |
| Workspace state | One window's destination, session selection and pane visibility; initially one workspace, later one per scene/activity instance |
| Native host | Containers, bars, gestures, insets, accessibility, lifecycle callbacks and capability reporting |

Start application-specific modules under `Python/logisticsmobile/`, with proposed
names such as `navigation.py`, `sessions.py`, `workspace_state.py` and
`platform_ui/`. Final names follow the implementation's actual boundaries.
`app.py` becomes a composition root rather than the owner of every feature's
mutable state. Existing callbacks can temporarily delegate to the coordinator
while feature views migrate incrementally.

Generic provider or reusable browser changes belong in commonUtils and follow
that repository's instructions. This plan specifies Logistics requirements; it
does not duplicate shared API documentation or require editing that repository
during planning.

### Native presentation adapters

Expose a narrow host contract: present destinations, activate a session, present
the open-item list, apply a layout mode, update commands/status, present a modal,
deliver navigation intent and dispose a workspace. Platform events become Python
commands; resulting Python state becomes view updates. Avoid an adapter that
mirrors every native widget API.

On Apple platforms, evaluate root `OptionContainer` first, then managed
`UINavigationController` stacks, `UITabBarController` sidebar behavior and
`UISplitViewController` for list/detail layouts. Check containment, safe-area
layout and Toga refresh behavior before selecting the controller composition.
Use the existing Rubicon Objective-C bridge for supported UIKit interfaces.
SwiftUI is an option if a measured gap requires a small compiled host, not an
assumed requirement for keeping the Python core.

On Android, evaluate the root `OptionContainer` with Material bottom navigation,
then a native navigation rail and list/detail host for wider windows. Use the
existing Java bridge where practical; add a small tracked Java/Kotlin helper when
native lifecycle or adaptive APIs require it. Compose is not required simply
because Android's adaptive examples use Compose. Verify compatible View-based
APIs and dependency versions before selecting them.

Do not scatter `_impl` access through feature code, edit installed backends, or
patch generated build products. Isolate necessary backend hooks in the adapters
and cover them with native checks. If a backend extension is necessary, package
and pin it reproducibly with a documented upgrade path.

### Resource and session identity

Opening the same canonical resource in the same workspace activates its existing
session. A name or a visible row number is not an identity. Two files with the
same name remain distinct. Identity includes the storage namespace and stable
resource identifier, with a provider revision recorded separately.

Importing an external provider document still creates a private copy. Its session
refers to that copy, not to an expired URL or content URI. Opening a remote item
uses the existing explicit download/private-copy workflow; the new UI does not
imply remote writeback or live editing.

During the initial implementation, permit one writable controller per resource
within the app. Reserve workspace IDs from the start so later windows can share
a controller or explicitly reject a duplicate writer. Multiple independent
writers must not bypass the existing conflict checks.

Do not retain every editor, WebView, decoded comic page and open archive forever.
Preserve session state while disposing inactive views and bounded caches. Measure
limits in the first prototype and define a concrete cache/resource budget before
enabling large collections of open readers. An inactive view can be recreated;
an unsaved in-memory private draft cannot be evicted silently.

### Recovery and privacy

Persist a small versioned workspace manifest containing safe session references,
open order, active selection and non-sensitive view state. Store ordinary drafts
in the existing document recovery mechanism; do not copy full drafts into the
workspace manifest. Publish changes atomically and validate schema, bounds,
identities and referenced resources during restore.

Keep decrypted LocalCrypt text, filenames, locations, thumbnails, passwords,
credential handles and sensitive reader state out of the ordinary manifest,
logs and native saved-state bundles. Initially omit private sessions from cold
restoration and require an explicit reopen/unlock. Do not add plaintext recovery
for private drafts. If private restoration is added later, it needs its own
encrypted persistence contract.

Preserve existing lock and forget semantics. Navigation may retain private work
in memory only while its credential session is valid; destructive close, lock,
forget or eviction must handle unsaved edits explicitly. Lock clears sensitive
views, caches and pending callbacks. Ordinary navigation must not accidentally
trigger a private-reader replacement that discards work.

Restore missing ordinary resources as unavailable entries with reopen/remove
actions. Preserve malformed recovery files and explain the failure. Respect the
existing restore preference rather than unconditionally restoring the last
active document; define the expanded preference's migration in milestone 2.

### Asynchronous operations and lifecycle

Every load, save, preview and download captures its originating session and a
generation/revision token. A completion cannot replace another session's view or
publish into a closed, locked or superseded session. Native widgets update only
on the UI thread. Maintain the Android cooperative event-loop integration.

Checkpoint ordinary edits during use; background and exit notifications are
additional opportunities, not the only recovery path. On memory pressure,
release disposable views and decoded images before document state. Process
termination restores ordinary work and leaves private sessions closed. Reconcile
interrupted saves/downloads before allowing retries rather than claiming that
background work necessarily completed.

## Navigation and adaptive behavior

### Back and close

- Apple Back follows the active navigation stack. Switching primary destinations
  preserves each destination's route.
- Android lets the system handle the keyboard first where applicable. App Back
  then dismisses the active modal/transient view, returns within the destination
  route, or returns from a document to the open-item list. At a destination root,
  allow the normal system exit behavior; do not cycle through tab selections.
- Back from a document leaves it open. **Close document** is explicit and separate
  from Back, locking a reader, and deleting a file.
- A cancelled swipe or predictive Back gesture must not commit navigation or
  trigger save/discard side effects. Check compatibility with the actual Toga
  activity and supported AndroidX/platform Back APIs.

For an ordinary dirty document, Close offers Save, Keep draft and close, Discard
changes, and Cancel. A retained draft stays available in saved/recent document
access. Discard changes resets recovery to the appropriate saved baseline without
overwriting a concurrently changed file. A save conflict keeps the session open
and offers the existing safe-copy workflow.

For a dirty private document, Close offers Save to its supported destination,
Discard and close, and Cancel. It does not promise durable Keep draft recovery.
Failed save, cancelled export or cancelled close leaves the session intact.

### Platform layouts

| Environment | Navigation and content target | Continuity requirement |
| --- | --- | --- |
| iPhone compact | Native primary tab bar, hierarchical Files navigation, open-item list leading to one document | Preserve selection, drafts and route when changing destinations |
| Duo compact and regular | System-managed bars adapt to supported poses; list/detail uses native size-class and available-space behavior | Opening/closing and rotating preserve the same session and position |
| iPad | Native tab/sidebar presentation where supported; open-item or file list beside content; collapses in narrow windows | Resizing changes presentation, not resource/session ownership |
| Android phone | Material primary navigation and one main pane, normal system Back | Keyboard, configuration callbacks and recreation preserve ordinary work |
| Android tablet or unfolded foldable | Adaptive native rail with list/detail where usable; collapse for narrow split-screen windows | Folding, multi-window resize and display changes retain state |

Treat Apple size classes, layout margins and safe areas as native inputs. Treat
Android window metrics/classes, insets and separating/occluding fold features as
native inputs. Do not identify a layout from the device's marketing name, assume
an unfolded device always has a wide app window, or share hard-coded phone
breakpoints between platforms. A separating hinge must not obscure content or
touch targets; a posture-specific layout is optional only where it improves use.

Use platform icons and labels for destination and command items. Preserve title
metadata for accessibility and overflow even when the visible item is an icon.
Keep Save As, Export and secondary commands in native menus; prioritize frequently
needed actions. Provide Dynamic Type/font scaling, screen reader order, adequate
touch targets, contrast, reduced transparency/motion support and keyboard access.
Use platform tap target conventions rather than one fixed pixel size everywhere.

## Milestone 0 Native integration proof

**Goal:** establish that both native hosts can support the proposed architecture
before a broad feature refactor.

1. Capture current builds, dependency versions, platform minimums, native UI cases
   and a before/after screenshot inventory. Inspect the generated native hosts,
   dependency resolution, activity/scene lifecycle and packaging boundaries.
2. Build a minimal Files/Documents/Settings host with real native navigation on
   iOS and Android. Use `OptionContainer` as root content where selected. Verify
   the required Material dependency, icons, tab changes and programmatic routing.
3. Prove an Apple navigation stack and one native list/detail composition with
   Toga content. Prove Android resize callbacks, rail placement and keyboard
   insets with equivalent content. Check recreation as well as live resize.
4. Build the Apple proof against the SDK needed for Duo, with modern APIs guarded
   and older-iOS fallback checked. Audit SDK-triggered compatibility changes.
   Decide whether to retain the existing framework pins or make a scoped upgrade.
5. Record callback cleanup, containment, focus, main-thread and memory behavior.
   Choose the smallest reproducible adapter/backend changes that pass the proof.

**Exit criteria:** native compact navigation works on both platforms; adaptive
container feasibility and any required backend extension are demonstrated; no
lost edits when attaching/detaching a view; the normal app and test-mode builds
both launch. Do not claim Duo support solely from an ordinary iPhone simulator.

## Milestone 1 Native shell in the actual app

**Goal:** replace the prototype shell while keeping every existing workflow
reachable.

1. Introduce destination IDs and per-destination routes in shared Python state.
   Add platform adapters and route the current feature entry points through them.
2. Replace Home with the Files location hub. Initially wire the existing local
   browser, remote workflow and LocalCrypt workflow rather than leaving empty
   placeholders. Reader/library and chat entry points live under Documents.
3. Keep current feature controllers behind the new shell while their ownership
   migrates. Preserve checkpoint failure handling and private unsaved-work guards.
4. Add native Back/modal handling and feature command publication. Keep selection
   stable on programmatic destination changes and re-entrant native callbacks.
5. Update staging, icons, dependency declarations, dummy-backend assertions and
   native UI checks. Replace assertions about the Home button tree with behavior
   assertions; do not delete feature coverage to make the new shell pass.

**Exit criteria:** all current workflows are reachable through three destinations
on iOS and Android; actual native navigation is verified; destination switching,
picker cancellation and keyboard layout preserve current work. Wide-screen
presentation remains usable while complete document panes arrive in milestone 2.

## Milestone 2 Shared open documents and first adaptive workspace

**Goal:** two text/Markdown documents can stay open independently on both
platforms, with an adaptive list/detail presentation.

1. Implement the session registry, identities, active selection, view state,
   commands and bounded versioned workspace manifest as pure Python.
2. Adapt the existing DocumentStore and editor callbacks to per-session state.
   Preserve encoding, line endings, conflict detection and checkpoints. Avoid
   handlers that use a global `current` after an asynchronous operation begins.
3. Add Open documents, Create, Activate, Close, Save, Save As and Export command
   handling. Duplicate opens activate the existing session. Keep stored documents
   and retained drafts accessible independently of the open list.
4. Preserve cursor/selection, editor scroll and Markdown mode across switches,
   restoring only within the capabilities proved by each native text view.
   Document any temporary view-state gap explicitly.
5. Show the open list followed by the editor on compact windows; show list/editor
   beside each other when suitable. Rebuild/dispose views without saving, closing
   or duplicating sessions as a side effect of layout changes.
6. Define migration from the existing last-document preference and data. Keep
   existing document/library files and UUIDs intact; preserve unreadable records.
7. Add stale-completion, close/cancel, restoration and memory-pressure checks.

**Exit criteria:** open A and B, edit both, switch through Files and Settings,
resize/rotate, background, terminate/relaunch and recover each ordinary draft.
Closing one does not affect the other; a conflicting save never overwrites external
changes. Android recreation and live configuration changes both pass. Apple
compact/regular transitions preserve the active item.

## Milestone 3 Reader and private session integration

**Goal:** the same Documents workspace can hold text, Markdown, EPUB and comics,
including supported encrypted offline resources.

1. Adapt ordinary library readers to session controllers. Preserve library IDs,
   bookmarks and the implemented chapter/page progress semantics.
2. Add provider-backed local and LocalCrypt session adapters. Separate metadata
   editors from content readers while keeping their dirty state under the owning
   session. Retain transactional Save As across supported storage boundaries.
3. Route downloads/imports through the registry; re-opening an existing copy
   activates it rather than producing accidental duplicates.
4. Retain or suspend inactive private sessions in memory under a measured budget.
   If an operation cannot coexist with a private session, surface that restriction
   explicitly and preserve the existing save/discard guard.
5. Make lock/forget invalidate sensitive sessions, names, views, cached images
   and pending callbacks. Ensure ordinary workspace restoration leaks no private
   content and does not silently reopen private work.
6. Bound reader resources; stress alternating large comics, EPUB WebViews and
   editors. Keep archive access streaming and dispose handles correctly.

**Exit criteria:** mixed open items switch without lost drafts/progress or stale
content; comic password retry/cancel/lock, LocalCrypt save conflicts and encrypted
Save As still pass on both platforms. Supported formats and size limits remain
those of the existing implementation until separately changed.

## Milestone 4 Unified Files and connections

**Goal:** location browsing feels like one Files workflow while retaining storage
capabilities and boundaries.

1. Present on-device managed files, private downloads, supported remote locations
   and LocalCrypt through common location routes. Add pinned folders using stable
   safe identities; do not persist decrypted private paths in ordinary preferences.
2. Preserve folder history, selected item, scroll, list/tile mode, search and sort
   when switching destinations. Expired credentials make a location unavailable
   rather than silently switching to a different provider.
3. Move credential import/remember/reload/forget and diagnostics into connection
   management. Offer an empty-state connection action from Files.
4. Publish provider-supported commands only. Remote browsing/download remains
   read-only; local mutations and LocalCrypt saves preserve existing verification,
   cancellation and conflict behavior.
5. Show operation progress near its origin and permit cancellation. Local-to-LocalCrypt
   or decrypted-copy operations retain their implemented explicit semantics.
6. Keep system import/export pickers distinct from internal browsing. General
   external-folder access or provider writeback is a separate future contract.

**Exit criteria:** opening from Files activates the correct Documents session;
returning restores browsing state. Connection failures, revoked access, cancelled
downloads and partial mutations preserve recoverable work and accurate status.

## Milestone 5 Reader and editor visual refinement

**Goal:** content receives most of the screen and commands remain discoverable.

- Text: compact title/status, native editing/selection/undo where supported,
  keyboard-aware commands and action menu. Recovery status differs from Save.
- Markdown: Edit/Preview on compact windows, optional side-by-side preview where
  space permits. Renderer parity with desktop requires separate sanitization and
  performance validation; it is not implied by a new layout.
- EPUB: readable type/margins, contents, bookmarks and appearance controls;
  optional exact-position persistence requires a new stable locator contract.
- Comics: fit-page, pinch zoom/pan, reading-order gestures and page navigation;
  optional two-page mode must respect reading order and available space.
- Files: native contextual actions and readable list/tile presentation, with
  thumbnails and menus retaining capability/privacy rules.

**Exit criteria:** complete the feature matrix below with native touch, keyboard,
screen reader and font-scaling checks. Gestures do not fight system Back or
scrolling; immersive reading offers a clear way to restore navigation.

## Milestone 6 Independent windows

**Goal:** add system-managed windows after the single-workspace model is stable.

For iPad, evaluate a maintained Toga backend extension or small native scene host
using `UIWindowScene`/scene sessions. Give each scene its own workspace selection,
routes, presentation and restoration. Remove singleton assumptions in picker
delegates, modal ownership, private-reader state and command targeting. Define
cross-window writer ownership, resource lifetime and save-conflict behavior before
shipping another window.

Android split-screen/resizing is required in earlier milestones. Multiple
independent instances of Logistics are a separate activity/task capability to
evaluate here; do not equate a navigation rail or two internal panes with two OS
windows. Apply the same resource ownership rules.

**Exit criteria:** creating, activating, closing and restoring windows preserves
their distinct UI state, targets commands correctly and never creates conflicting
writers or shares decrypted views accidentally. Enable only on verified platforms;
no independent Duo window capability is assumed from its larger display alone.

## Validation and release gates

Add coverage at the layer that can prove the behavior. Python tests cover session
and recovery invariants. Toga dummy tests cover host integration. Native tests
cover actual containers, focus, bars, WebViews/images, lifecycle and navigation.
Real document-provider permissions and physical-device gestures need separate
manual/device evidence. Build success does not substitute for those checks.

| Scenario | Required result |
| --- | --- |
| Two ordinary text drafts | Independent text/name/state survives switch and restart |
| Duplicate names and repeated opens | Correct identity selected; repeated open does not create another writer |
| Save conflict and failed Save As | Source preserved, draft retained, correct session owns the result |
| Back, cancelled gesture and Close | Back preserves the item; cancellation has no destructive side effect |
| Files and destination switching | Folder/history and document selection preserved independently |
| Markdown mode and rendering | Correct session rendered; existing offline restrictions maintained |
| EPUB and CBZ/ZIP | Chapter/page progress, bookmarks and current password rules preserved |
| LocalCrypt and credentials | No plaintext restoration/log leakage; dirty-close and lock guards pass |
| Remote download/cancel/offline | Current access model preserved; no implied upload or provider writeback |
| Stale completion and disposed views | No wrong-session update or resurrection after close/lock |
| Low memory and large archives | Bounded decoded caches and native resources; no silent private-draft eviction |
| Rotation, folding and resizing | Same active resource, ordinary draft, usable controls and stable position |
| Background and process termination | Ordinary recovery works; private sessions require reopen/unlock |
| Picker success/cancel/revocation | Correct source scope and unchanged source; no leaked permission handles |

Minimum device coverage: compact iPhone on the retained minimum where testable
and current iOS; Duo compact/regular and representative poses on its supported
simulator/device; iPad in wide and narrow resizable windows; Android phone,
tablet and foldable in compact/expanded and split-screen configurations. Cover
the chosen Android minimum/current API, gesture and button navigation, software
and hardware keyboard, large text, RTL, light/dark and screen readers. Record
unavailable environments as unverified rather than substituting generic resize
tests for device-specific support.

Preserve all existing document/runtime/native UI cases and desktop portability
boundaries. Extend the explicit smoke/native evidence inventories and verifier
when cases are added. Stage new modules/resources through the whitelist; validate
normal and test-mode builds. Retain clean source fingerprints for accepted release
evidence and label local development runs separately. Use the established release
process and platform gates; this plan does not itself authorize a release.

## Implementation sequence and first deliverable

Use small reviewable changes in this order:

1. Native integration proof, compatibility decisions and reproducible adapter
   foundation on both platforms.
2. Native shell and routes, with existing workflows preserved.
3. Pure Python session/restoration model and meaningful invariant tests.
4. Two text/Markdown sessions, open-item UI, close/save semantics and adaptive panes.
5. EPUB/comic and provider-backed/private session adapters.
6. Files/connection reorganization, followed by reader/editor visual refinement.
7. Independent windows after shared ownership and lifecycle requirements pass.

The first end-to-end deliverable combines milestones 0 through 2: native
Files/Documents/Settings, real Files entry points, two editable text/Markdown
documents, compact open-item navigation and an expanded list/editor workspace on
Apple and Android. Existing reader, chat and remote workflows stay reachable
during migration. Both mobile targets must pass the relevant checks before this
foundation is treated as complete.

Update this plan's milestone status as work lands. Document implemented user
changes in `Python/logisticsmobile/user_docs/README.md`, preserve its `index.md`
compatibility entry, and update architecture/evidence in `mobile-preparation.md`.
No root README capability change is needed until behavior ships. Preserve the
desktop navigation fallback and external-feature documentation boundary.

## Platform references

- [Apple Duo layout guidance](https://developer.apple.com/videos/play/tech-talks/111466/)
  describes size-class-based adaptation and continuity. Use native layout inputs
  rather than designing a layout per device pose.
- [Apple Duo bars](https://developer.apple.com/videos/play/tech-talks/111462/)
  describes SDK adoption and managed navigation containers that adapt bars to
  supported poses. Custom standalone bars do not establish the same behavior.
- [Apple tab and sidebar integration](https://developer.apple.com/documentation/uikit/elevating-your-ipad-app-with-a-tab-bar-and-sidebar)
  and [split views](https://developer.apple.com/documentation/uikit/uisplitviewcontroller)
  provide the Apple presentation patterns to evaluate.
- [Apple window scenes](https://developer.apple.com/documentation/uikit/uiwindowscene)
  provides independent UI-instance lifecycle; session ownership remains app work.
- [Android navigation patterns](https://developer.android.com/design/ui/mobile/guides/layout-and-content/layout-and-nav-patterns)
  recommends primary navigation appropriate to window size, including rails for
  larger windows. The shared three-destination model fits this structure.
- [Android configuration handling](https://developer.android.com/guide/topics/resources/runtime-changes)
  explains recreation and configuration callbacks. Both require state handling,
  including hosts that consume some changes themselves.
- [Android foldable guidance](https://developer.android.com/develop/adaptive-apps/guides/foldables/learn-about-foldables)
  covers adaptive layouts and continuity; verify bridge-compatible APIs when
  implementing fold features.
- [Android predictive Back](https://developer.android.com/guide/navigation/custom-back/predictive-back-gesture)
  provides native Back integration requirements.
- [Toga OptionContainer](https://toga.beeware.org/en/stable/reference/api/containers/optioncontainer.html)
  documents mobile root placement and the Android Material dependency. Check the
  selected pinned backend as well as current documentation before implementation.
