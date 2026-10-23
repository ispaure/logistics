# Mobile architecture assessment and roadmap

[Developer index](development.md)

Assessment date: October 14, 2026. This roadmap covers reader controls,
session ownership, reusable native UI, and Books/Comics feature organization.
The proposed changes preserve the Toga mobile interface and the Qt desktop
interface while making their shared logic and platform boundaries clearer.
Implementation should begin with explicit session ownership, because extracting
components before resolving their reliance on app-wide state would export that
coupling into new packages.

The assessment below records the pre-refactor baseline and delivery plan. The
local implementation status describes the resulting code. Keep changes local
until the user authorizes commits and pushes.

## Local implementation status

The subsequent host restructuring gives text Open/Save As a composed
`EditorPicker` in `mobile.editor_picker`, with state and cancellation
owned outside `FilesUI`. Saved-import inventory/deletion is now a composed
`SavedFilesController`, rather than an application mixin. `composition/assembly.py`
installs enumerated compatibility accessors; `services/workflow_host.py` declares
read-only host capabilities and explicit writable state descriptors.
See the [mobile module/test map](mobile-runtime.md) for the
current boundaries, payload registrations and worker invalidation contract.
These changes have host-level verification; they do not replace native evidence
for actual Open/Save As layout, Back and encrypted transfers.

The October 16 cleanup consolidates library and provider gesture scheduling in
`mobile.reader_controls.schedule_swipe`. Both spread-relative and
absolute-page gestures reject busy, closed and inactive-host sessions and retain
one in-flight task. Format adapters still choose spread targets, store progress,
report read failures and enforce their own private-content policies.
`ReadingFrame` also owns the EPUB restore-controls button across repeated
immersive transitions; comics retain their image gesture for restoring controls.

Retained import inventory/deletion lives in `mobile.saved_files_ui`,
separate from preference rows and installed-build information in `mobile.settings`.
The new owner is explicitly included in the curated payload list. Its existing
multi-window, busy-reader, confirmation and original-source protections remain
part of the deletion workflow. The Settings page remains named Saved books &
comics because its inventory covers retained CBZ/EPUB imports and their records.
Single-item and Delete all local copies actions share the same deletion path;
bulk deletion confirms the measured inventory once, rechecks window/reader state,
closes affected sessions and forgets Recent and source-import mappings. Local and
LocalCrypt collections are outside this inventory. Failed inventory entries are
preserved, and a deletion failure reports how many copies were already removed.

The native acceptance runner composes document, reader, chat and connection
workflows. Reader import/password/large-archive cases now sit with the existing
native reader geometry checks in `reader_checks`; WebView readiness is shared
through `web_checks`. The ordered 31-case contract and exact-source/backend
verification remain mandatory. Scenario extraction does not convert host checks
into native evidence or remove any acceptance assertions.

The core cleanup is implemented locally in the delivery order below. Reader
controllers now use enumerated host services rather than broad app fallback or
state publication. Provider cancellation/busy state belongs to its controller;
reader tools have a separate route before Back returns to the originating folder.
The shared reading frame and page commands preserve separate library/provider
progress, bookmark and cleanup policies.

Books owns mobile chapter rendering/presentation under `features/books/mobile`;
Comics owns mobile image validation/presentation under `features/comics/mobile`.
The mobile catalogue remains host-owned and is separate from reader UI.
Optional native image canvas, configurable navigation, route containment and
chrome restoration now live in `commonUtils.ui.native`, with its Android Java
bridges and packaging documentation in the shared repository. The obsolete
Logistics canvas/navigation/routing implementations have been removed.

Host composition, private-content policy, adaptive document workspace and scene
writers remain Logistics responsibilities. The delivery milestones have local
implementation and integration evidence in the [mobile UI refresh guide](mobile-ui-refresh.md#mobile-architecture-cleanup),
including iPhone/Android/iPad native runs and physical iPhone screenshots/geometry.

## Baseline boundaries and assessment

| Area | Current owner | Assessment |
| --- | --- | --- |
| EPUB package parsing and resource resolution | `Python/features/books/epub.py` | Useful portable core already reused by mobile |
| Comic archive access, page ordering and metadata | `Python/features/comics/{archive_io,library,pages,comicinfo}.py` | Useful feature ownership already reused by mobile |
| Desktop reader presentation | Books reader modules and Comics reader/UI modules | Qt presentation can remain separate from Toga |
| Mobile catalogue, progress records and book/comic views | `mobile/{library,library_ui,reading,reader_chrome}.py` | Format ownership and presentation are mixed across a broad mobile package |
| Provider-backed readers and editing | `mobile/{localcrypt,localcrypt_ui,private_sessions,file_resources}.py` | Storage/security decisions are important; several reading controls duplicate ordinary readers |
| Reader sessions | `reader_sessions.py` and `private_sessions.py` | Controllers exist, but publish compatibility attributes onto the app and fall back to it dynamically |
| File browsing | `commonUtils.ui.native_browser` with Logistics `browser_ui.py` and `files_ui.py` | Good shared-component/host-policy boundary, though the subclass reconstructs parts of shared presentation |
| Native navigation and image gestures | `native_navigation.py`, `routing.py`, `adaptive_workspace.py`, `comic_canvas.py`, Android bridges | Reusable mechanisms remain coupled to Logistics destinations, callbacks or packaging |
| Build and source selection | `mobile_build/tools.py`, `cloud_build.py`, `pyproject.toml` | Explicit staging prevents the mobile app from importing the entire desktop application; moves must update this boundary |

Mobile is mostly Python. Toga provides the cross-platform widget interface;
Python adapters also use Rubicon/Objective-C access on Apple platforms and Java
access on Android. The tracked Android `ComicView.java` and `NavigationBack.java`
provide specific native behavior. The rclone bridge is Go. Moving a Python adapter
alone does not relocate its native source or build integration.

The dependency separation is stronger than the controller separation. Mobile
already reuses portable feature modules and shared providers without booting the
desktop UI. The main maintenance cost is duplicated reader presentation and
implicit access to whichever controller last published state onto the app.

## Intended ownership

| Owner | Responsibilities after cleanup |
| --- | --- |
| commonUtils | Optional reusable Toga widgets and native adapters; resource/provider and persistence primitives; no Logistics imports |
| Books and Comics | Format-specific document models, reading behavior and platform presentations; no app-wide destination or transfer policy |
| Logistics mobile host | Catalogue/import workflow, document sessions, Files/Documents routes, preferences, transfer integration and private-content policy |
| Mobile build tools | Package selected portable/Toga sources and native bridges; verify source identity and device signing |

Dependency direction should be: mobile host → feature controller/presentation →
portable feature core and optional shared widgets. commonUtils must never import
Logistics features or read Logistics configuration. Portable feature imports must
not load Qt, Toga, Rubicon or Java.

The combined Books & Comics catalogue can stay in the mobile host. Its app-private
UUID storage, import records and workspace integration are host concerns. EPUB
rendering belongs with Books, comic presentation with Comics, and toolkit-level
image gestures with commonUtils. Feature ownership does not imply that every
mobile file belongs under `features/`.

## Point 1 Consolidate ordinary and private reader controls

### Baseline findings

`LibraryUI` inherits `ReaderChrome`, which owns reading mode, contents/bookmarks,
appearance and page actions. `LocalCryptUI` separately implements private tools,
bookmark controls, page swipes and reading mode. Both use the native comic canvas.
Thus image gestures are already shared, while surrounding controls and lifecycle
handling are only partly shared.

Ordinary library progress/bookmarks are stored by `LibraryStore`; private reader
bookmarks remain bounded and memory-only. Provider sessions also cover ordinary
local text, so the name "private" is not a reliable substitute for storage type
or supported operations. A common UI must obtain those decisions explicitly.

### Proposed change

Introduce a Logistics-owned reader presentation component with explicit state and
commands: title, position/count, contents, bookmarks, busy/error status, appearance,
fit-page and reading-mode actions. Give it capabilities such as whether metadata
editing or locking is available. Keep actions bound to a specific controller.

Use adapters for library-backed and provider-backed readers. Each adapter owns
page loading, progress storage, bookmark behavior and cleanup. The presentation
must not choose those policies by checking a remote name, folder label or class
name. Start with comics, whose duplicated page/control behavior is clearest, then
reuse applicable controls for EPUB. Text editing remains a separate view.

Share controls and layout within Logistics first. Do not put this entire reader
component in commonUtils: it still embodies Logistics document commands and
capabilities. The generic image widget is the separate Point 3 extraction.

### Migration and completion checks

1. After Point 2 establishes explicit ownership, define the minimal reader state
   and command contract from the two existing implementations.
2. Adapt ordinary comic reading while preserving its progress/bookmarks and
   chapter/page bounds. Adapt provider comic reading using the same controls.
3. Consolidate controls, page status and immersive layout; retain separate
   backend operations and private cleanup. Adapt EPUB controls where applicable.
4. Delete the replaced control/layout implementations after their callers have
   migrated. Keep distinct platform renderers where their output requirements differ.

Completion requires identical comic control behavior for Local and LocalCrypt,
with expected differences in locking, persistence and encrypted writes. Validate
left/right and manga-direction swipes, zoom-versus-paging, first/last page bounds,
rapid commands, failed reads, bookmark limits, theme changes and repeated
fullscreen reentry. Suspended private images/previews must be cleared without
losing an unsaved draft. Pulling must not disable independent offline reading.

Effort: medium. Main risk: accidentally sharing persistence or cleanup policy
along with the controls. Benefit: future reader UX fixes apply to both paths.

## Point 2 Make session and controller ownership explicit

### Baseline findings

`Readers.publish()` and `PrivateSessions.publish()` copy lists of controller
attributes onto the application. Their controllers use `__getattr__` to obtain
unspecified dependencies from the app. `PrivateController.__setattr__` can also
publish its cancellation object onto the app. These mechanisms make ownership
depend on the active controller rather than the callback's originating session.

Useful safeguards already exist: workspace identities/generation tokens,
navigation-generation checks, private operation handling and exclusive scene
writers. Preserve these rather than replacing the workspace wholesale.

`ReaderController.show_view()` currently supplies a reader route and title itself
without forwarding the incoming route arguments. Reader tools and appearance need
an explicit distinction between returning to the reader and returning to the
folder. An origin destination alone is not a complete route contract.

### Proposed change

Give each controller its session, resource adapter, reader state, widgets and
operation lifetime. Pass host services explicitly: present a route, update the
document list, read/save preferences, report status and obtain loop/worker access.
The app should hold managers and controllers, not copies of their mutable fields.

Separate session identity from presentation origin. A session can be activated
from Files or Documents while retaining the same resource identity. Represent
reader, tools and appearance as distinct routes associated with that session;
retain the browser panel rather than serializing a folder merely to reconstruct it.

Commands and asynchronous completions must retain the originating controller and
workspace token. Operation cancellation belongs to that operation/session. Transfer
cancellation remains independently owned. A late completion may update a still-live
session but must not take over a newer selection or revive a closed session.

### Migration and completion checks

1. Inventory `FIELDS`, dynamic app fallbacks and all app-level `book_*`/`crypt_*`
   consumers, including cloud opening, Save As, hub activation, memory pressure,
   scene transitions and tests.
2. Introduce explicit host services and controller state without changing disk
   formats. Migrate one ordinary reader path, then provider readers.
3. Replace active-reader aliases in hub, cloud, file and close commands with
   explicit controller lookups or origin-bound callbacks. Distinguish global
   commands such as Continue from actions originating inside a specific view.
4. Move cancellation and busy state behind operation ownership. Preserve the
   existing allowance for offline local reads during a transfer.
5. Remove publication lists and broad app fallback after all consumers migrate.
   Any temporary compatibility adapter should have an enumerated removal list.

Completion requires two-reader switching with an in-flight read, close during
work, memory-pressure suspension, provider draft retention, Save As on the correct
document, Files → reader → tools → reader → original folder, and Documents-origin
activation. Recheck scene writer exclusion and protected-content restrictions.
Maintain current ordinary recovery/restoration and transient-session omission.

Effort: medium to large. Main risk: a missed compatibility consumer or stale
callback. Benefit: changes become local to a document instead of active app state.

## Point 3 Extract reusable Toga and native components

### Candidates and boundaries

| Candidate | Recommendation | Required boundary |
| --- | --- | --- |
| `comic_canvas.py` plus Android `ComicView.java` | Extract first as a generic native image canvas | Image/geometry input, fit/zoom/pan and gesture callbacks; comic ordering and loading stay with features |
| Native destination navigation and route containment | Extract after controller cleanup | Caller-supplied destinations, labels and callbacks; no Home/Files/Documents/Settings constants in shared code |
| Native memory subscriptions | Small later extraction | Generic subscribe/dispose callbacks; host chooses which resources to release |
| Appearance and safe-area mechanisms | Assess existing shared appearance APIs first | Separate native mechanism from Logistics colors, reader choices and transfer banner policy |
| Adaptive document workspace | Keep host composition initially | Extract only proven split/rail mechanisms; document lists and scene ownership remain Logistics policies |
| Browser presentation customization | Improve shared configuration after reader cleanup | Explicit rendering/options hooks rather than dependence on private widget layout |

The navigation extraction spans `native_navigation.py`, `routing.py`, portions of
`adaptive_workspace.py`, fullscreen chrome handling and `NavigationBack.java`.
It is larger than moving one module: native lifecycle, keyboard handling,
safe-area ownership and layout listeners must remain coordinated.

### Packaging and migration

1. Read commonUtils' own `AGENTS.md`, developer map and existing API documentation
   before implementing an extraction. Its documentation and commits belong there.
2. Define an optional Toga namespace using commonUtils' existing organization.
   Select the backend explicitly; operating system alone is insufficient because
   macOS can run either the Qt application or a Toga host.
3. Extract the canvas using a minimal consumer that imports no Logistics modules.
   Move/include Android native source under shared ownership, with an explicit
   consumer packaging contract. Adjust Java imports and source-set configuration;
   remove the duplicate Logistics bridge after migration.
4. Update shared source staging and Logistics `mobile_build/tools.py`, Android Gradle
   configuration, tests and source hashing. Confirm packaged native source is
   included in the exact-source evidence contract.
5. Extract navigation in separate increments: configurable destination state,
   native containment/Back, then the necessary layout and chrome mechanisms.
   Logistics continues to decide whether navigation is allowed and what Back means.

Toga dependencies and backend imports must stay lazy/optional. Shared headless
operations and desktop Qt startup must work without Toga installed. A minimal
Toga host must use each extracted component without importing Logistics. Test
dispose/recreate behavior so listeners, delegates and views do not survive their host.

Native acceptance includes fresh generated Android packaging, native Back,
rotation/resizing, keyboard show/hide, dark mode, zoom gestures and repeated
fullscreen/route transitions. Check iPhone and iPad safe-area/layout behavior,
Android phone/tablet layout, and the paired physical iPhone screenshots. Emulator
success alone does not establish physical Android gesture behavior.

Effort: medium for the canvas, large for navigation. Main risk: cross-repository
packaging and lifecycle regressions. Coordinate with current commonUtils work;
use a fixed source snapshot for each validation/build rather than including
concurrent changes accidentally.

## Point 4 Align mobile presentation with Books and Comics ownership

### Baseline findings

Portable EPUB/comic models are already in their feature packages. The mobile
`reading.py` combines image validation with EPUB HTML presentation, while
`library_ui.py` combines catalogue and reading UI. Desktop Books also has its own
chapter conversion in `content.py`, which targets Qt rich text. Mobile WebView
output has different offline/CSP and size requirements; merging those renderers
verbatim would lose an important boundary.

The feature package initializers defer registration imports. Preserve this so
importing a portable module never initializes desktop contributions or widgets.

### Proposed organization

Use `features/books/mobile/` for Toga EPUB presentation and
`features/comics/mobile/` for Toga comic presentation. These are proposed package
names; keep existing public desktop module paths stable during the migration.
Place renderer-specific chapter generation with Books and comic validation with
Comics unless an existing shared format API clearly owns the generic portion.

Keep the shared reader-control component in a small Logistics presentation owner
until both feature adapters can consume it without circular dependencies. The
mobile host imports the feature adapters and supplies contracts/services; feature
adapters should not import `mobile.app`. If a genuinely shared reader
contract is needed, place it in a neutral Logistics module with no toolkit imports.

Keep catalogue records, app-private import storage, workspace identity, credential
decisions, LocalCrypt decryption and transfer orchestration in the host. Private
and ordinary resource adapters can feed the same feature presentation without
putting encryption workflows into a comic widget.

### Migration and completion checks

1. Once Points 1 and 2 stabilize contracts, split catalogue presentation from
   reader presentation. Move EPUB and comic adapters independently.
2. Move mobile chapter rendering from `reading.py` into Books while preserving
   its inert offline output and resource limits. Compare shared parsing/sanitizing
   primitives with the Qt renderer; share proven primitives, keep output adapters.
3. Move comic-specific validation and reader presentation into Comics; keep the
   native canvas dependency optional. Preserve password-protected reader policy.
4. Update imports, test patch targets, staging whitelists and feature documentation.
   Remove old forwarding modules once their consumers migrate.

Completion requires desktop EPUB/comic regression tests, portable imports with UI
toolkits blocked, packaged mobile startup, WebP/JPEG/PNG reading, protected archive
handling, metadata and progress preservation, and ordinary/private parity. Package
moves must not rename stored provider identities, UUIDs or state files.

Effort: medium after ownership cleanup. Main risk: import cycles or accidentally
staging desktop-only UI. Benefit: future EPUB/comic changes have an obvious owner.

## Delivery sequence

| Milestone | Deliverable | Dependency | Completion gate |
| --- | --- | --- | --- |
| M0 | Record baseline contracts and source snapshot | Current local work | Preserve known Back/fullscreen/transfer behavior and existing data formats |
| M1 | Explicit controller state, services and operation ownership | M0; Point 2 | No reader-state publication or broad app fallback; origin-bound async checks pass |
| M2 | Shared reader controls with library/provider adapters | M1; Point 1 | Same comic UX on Local/LocalCrypt, with distinct storage/cleanup policies |
| M3 | Books/Comics mobile adapters and rendering ownership | M2; Point 4 | Portable, desktop and staged mobile imports pass; no circular host dependencies |
| M4 | Shared optional native image canvas and packaged bridge | M2, coordinate with M3; Point 3 | Independent consumer, fresh Android build and physical iPhone layout checks pass |
| M5 | Shared configurable navigation and lifecycle adapters | M1–M4; Point 3 | Native Back, keyboard, split/rail, cleanup and fullscreen checks pass |
| M6 | Integration review and removal of temporary adapters | M1–M5 | Complete validation matrix and matching local device build |

M1 and M2 provide the largest immediate maintenance benefit. M4 is the clearest
commonUtils extraction. M5 should proceed only with the independent-consumer and
packaging contract established; moving app-specific navigation merely to reduce
the mobile package size would not satisfy its gate.

Deliver one reviewable behavior or ownership change at a time. Keep implementation
and mechanical package moves separate so regressions can be isolated. This plan
requires coordinated changes in Logistics and commonUtils, but does not require
a new framework, a Swift rewrite or a switch to PySide on mobile.

## Validation and documentation

Existing tests to retain include `mobile_build/tests/reading/test_reader_sessions.py`,
`test_mobile_ui_workflows.py`, `test_files_ui.py`, `test_window_owners.py`, and
`Python/tests/test_mobile_{readers,localcrypt,workspace,portability,packaging}.py`.
Native checks cover reader behavior, LocalCrypt, navigation and browser Back.
Add tests for ownership/cancellation and component independence where current
tests rely on app aliases; do not merely rewrite assertions to match moved code.

Use synthetic files and remote names. Cover ordinary library, direct Local and
LocalCrypt resources; Files and Documents origins; reading, drafting and transfer
concurrency; suspend/resume, close and failed operations. Reopen pre-refactor
ordinary records/recovery data to demonstrate compatibility. Check that private
bytes, titles and memory-only bookmarks do not enter ordinary recovery/manifests.

Run portable/headless checks and focused host tests during each milestone. Run
desktop feature tests for feature moves and fresh native builds for shared bridge
or packaging changes. At integration, run the full mobile host/native suites and
the affected desktop suites. Deploy the matching validated snapshot locally to
the paired iPhone and inspect repeated fullscreen and Back transitions. State any
physical Android or scene behavior that remains unverified explicitly in evidence.

Update Books/Comics user guides only for changed user-facing behavior. Record
Logistics contracts here and in the existing mobile developer guides; document
new shared APIs in commonUtils itself. Add setup documentation only if dependency
installation or build steps change. Keep root README and optional external feature
documentation boundaries intact.
