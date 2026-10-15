# Mobile workspace drawers and paired documents

The mobile `FileBrowser` bounds List and Tiles at 500 entries per page using the
shared browser's `page_size` property. Paging controls precede the rows inside
the scroll content so the bottom destination bar cannot cover Next at the end
of a listing. Row command binding uses one button-to-entry map per render,
avoiding repeated filtering and sorting for every row. Generic folder glyphs
require no image reads; the shared renderer omits empty image widgets when
thumbnails are disabled. Thumbnail loading retains its revision-aware RAM bounds.

`workspace_navigation.py` owns feature-level layout inside the existing
commonUtils native tab and navigation stacks. The host retains native Back,
keyboard safe areas, immersive-reader chrome and independent window ownership.
It no longer installs the earlier Documents-only UISplitViewController. Settings
and Chat remain full-screen destinations; chat configuration is a full-screen
route in Chat.

`WorkspaceFrame` keeps each original editor/browser Box as its route view. Its
existing children move into a retained content Box, with a top-left hamburger
and a horizontal content area. Transfer banners retain their original registered
parent. Compact drawers retain the main content at its original width and insert a
browser up to 320 points/dp wide, leaving at least 64 points/dp of the page visible.
The row clips overflow. UIKit animates a snapshot of the previous row to reveal
the new layout, respecting Reduce Motion; the actual editor retains its owner.
Android uses the same retained layout without the UIKit transition. Root scroll
overviews receive a Box frame too, so their hamburger toggles in place.
On Apple, the frame moves its menu and Split control into the existing native
navigation bar, preserving Back and eliminating the extra in-content header.
The 52-point menu uses UIButtonConfiguration glass when available, with a gray
capsule fallback. Destination selection renders against its explicit destination
because native selection callbacks precede the host state commit; UIKit Back
also schedules a workspace render. At 640 points/dp, the file browser and document each receive half the
actual content width. The same measured-window rule drives Chat's conversation
list and message area; it does not infer device type from a name.

The file drawer has independent browser state over the shared bounded browser
and ResourceSelection APIs. Its roots are local files and available LocalCrypt
copies. Remote connection/mapping operations stay in the existing folder hub.
Enumeration runs in a worker, rejects superseded folder/storage results, and
serializes scheduled refreshes. Opening files uses the existing provider-session
or library import path and preserves the destination where the user opened it.
It does not modify the Folder Hub tab's selected resource or reuse transfer cancellation
handles. Failed enumeration disables stale file opening.

In Documents, Split chooses another open editable text/Markdown session. The
current session becomes the left-hand pinned editor; the selected session is the
right-hand editor. Each widget has one native parent. Reparenting borrows the
existing owner rather than cloning its text, draft or callbacks. The hamburger
temporarily substitutes the file browser for the pinned editor. Narrowing keeps
the selected document and retains the other session. Closing a pinned session
clears its presentation; editor commands rebind to their actual owner and can
swap the active/pinned sides. Books and comics retain their existing reader
lifecycles and are not paired by this text-editor command.

Conversation selection uses stable conversation IDs, preserves unsent drafts,
and disables conversation switching during a request. Generation settings and
export commands remain available from Chat. No model request starts from
navigation. The conversation list represents the existing flat conversation
store; no new folder or branching persistence format is introduced.

Host coverage is in `Mobile/tests/test_workspace_navigation.py`, including
compact drawers, nested-file opening, independent drafts, two-document/browser
switches, collapse and close, and chat history/draft restoration. The native UI
review calls `workspace_checks.py` to exercise real phone/tablet content and
capture the file drawer, paired documents, conversation list, Chat and Settings.
Wide native checks assert that actual pane widths differ by at most two points.
Evidence must identify the staged source; a simulated width in a host test does
not establish native Duo fold-gesture support.

## Folder Hub and file browser naming

Reader and preview menus use `mount_native_menu` to occupy the same UIKit
navigation-item slot as Documents, with native Back preserved. Android retains
the in-content control with the Documents inset. Normal reading frames participate
in measured floating-tab clearance; fullscreen comics retain zero margins. The
base inset comes from `ReadingFrame`, so repeated renders do not accumulate
bottom padding. Comic canvases flex to the current pane instead of pinning a
width measured before entering fullscreen.

The physical iPad check on 2026-10-15 used a cache-only synthetic comic and a
transient workspace session. All ten samples passed: the first fullscreen open
and repeated reopens occupied the complete 834-point safe width at x=0; normal
controls used the native Documents menu slot and left reading status 16 points
above the destination-bar boundary. The diagnostic restored ordinary startup
after cleanup. Detailed local measurements are retained in ignored
`Mobile/logs/ipad-reader-layout.json`. This does not establish the cause of the
user's original intermittent Folder Hub failure.

Folder Hub constructs discovery results and its replacement page before clearing
the existing root. Discovery failures show a recovery page with Refresh, local
browsing and Connections instead of an empty tab. Refresh can retry after credentials
change. Credential selectors guard transient native row indices and compute the
visible selection before clearing folder rows. Regression tests inject LocalCrypt
discovery failure during tab entry and transient credential-selection indices.

The `files` destination key remains stable for routing and session origins; its
visible name is **Folder Hub**, with the desktop three-row hub glyph in navigation
and on Home. Its root lists logical folders. Selecting a row opens the preferred
available copy directly. The adjacent actions button opens `folder-options`,
where Browse Local/LocalCrypt/Remote selects an explicit copy. Pull/Push remain on the folder action page. Browser return links and the
drawer’s folder-management shortcut are labelled Folder Hub. The Documents drawer offers browse roots, recent identities, discovered libraries
and creation shortcuts. Browse roots and libraries mount the independent file browser
in the main route. The Folder Hub drawer implementation remains available, but its
hamburger is not mounted.


## Mobile feedback follow-up (historical, superseded by the UX passes below)

Home suppresses only its own Apple navigation bar; its bottom tab stays visible.
`hub_ui` owns padded format-launcher cards, category filters and the open-session
overview. The stored-document listing is removed. The Archives launcher selects
ZIP/CBZ/EPUB files for current readers; no general archive manager is claimed.
Bundled Qt-free glyphs are rendered from the existing desktop `DestinationIcon`
geometry. `install_folder_hub_icon` applies the hub image to Apple tabs and both
Android navigation presentations without changing commonUtils.

`folder_tree` builds every dash-separated parent level while leaves keep original
folder-choice keys. Collapsing is presentation only. The Credential selector starts
at All and uses existing ZIP-to-remote associations; filtering retains every
available copy of each matching folder. Credential changes refresh in place.
Folder options remain a destination-local route. At 640 points/dp they pair a
retained folder picker and scrollable actions, with the row split equally and no
second outer inset on the picker. Narrowing restores actions alone. Mapping-removal
commands are absent from this page; transfer and deletion contracts are unchanged.

Documents keeps the menu and main browser as separate widgets to avoid borrowing
a widget twice. Library shortcuts retain the discovery provider (including pulled
crypt namespaces) and reject changed credentials. Clearing private catalog state
invalidates drawer enumeration, clears private browser rows and rebuilds the menu.
`RecentDocuments` stores at most six provider/resource/kind triples in each
window's private workspace. It omits titles and transient/provider-session entries,
preserves malformed history, and can reopen a closed ordinary document or book.

Chat reserves the actual overlap between the native tab bar and the content
viewport. This handles floating bars extending above UIKit's reported bottom safe
inset, both before and after keyboard layout. It does not add a second keyboard
inset. The native workspace checks cover Folder Hub pane widths and composer
clearance in addition to retained editor ownership.

Validation: 183 mobile host tests and 52 portable mobile tests (three expected
platform skips), plus lint and whitespace checks. Targeted native probes used the
existing simulator executable with the current Python UI sources: iPhone category
cards, folder nesting/collapse/credential filtering, matching library shortcuts,
and composer bounds/hit testing with keyboard and six-line drafts; wide iPad
Folder Hub panes measured 405/405 points and met at x=417 in an 834-point window.
These are targeted local checks, not full native-suite, Android-rendering,
physical-device or Duo fold-transition evidence. Probe sources, screenshots,
results and source hashes are retained under `Mobile/logs/feedback-review/`.


## iPhone tab labels at cold start

After installing the app-owned Folder Hub glyph, `navigation.refresh_apple_tab_items`
creates a fresh `UITabBarItem` for each wrapped navigation controller, using the
final destination title and image, then refreshes the native tab array. This avoids
reusing the original OptionContainer items' compressed label geometry on iOS 26.
The change does not select destinations, initialize Chat or change the route stacks.
No private UIKit label classes or frame writes are used by the application.

An iOS 26.5 cold-start probe reproduced Folder Hub at 24.3 points wide despite a
55.3-point intrinsic width; selecting it repaired the label. With fresh items, all
five labels fit before any selection, and their heights increase from the clipped
7–8 points to 12 points. Cold-start label checks passed on iOS 26.5 and 27.0.
Native suite startup now inspects rendered iPhone label bounds before it exercises
navigation, and host coverage verifies titles, glyphs and selection preservation.
The iPad's hidden legacy tab labels are excluded from the phone-only pixel check;
its visible native tab/sidebar presentation is checked separately. Local captures
and measurements live in `Mobile/logs/tab-label-review/`.


Validation for this fix: 185 mobile host tests passed, including startup from the
staged payload and title/image/selection preservation. Targeted native probes
passed phone cold-start bounds on iOS 26.5 and 27.0 and iPad tab/sidebar selection.
The signed update was installed in place on the paired iPhone; a physical-device
capture showed all five complete labels. That capture was on Documents, so the
before-selection assertion specifically comes from the cold-launch simulator
probes, not the physical screenshot. Lint and whitespace checks passed.


## Credential retention and compact interaction follow-up

Credential group labels come from the persisted ZIP-to-remote associations and
are seeded from the protected vault label when restoring older saved credentials.
Known but locked remotes stay available in Folder Hub. Action entry points check
that a remote is loaded and, for mapped folders, matches its connection identity.
Session imports retain the original ZIP via CredentialPackages: AES-256-GCM in
the native bridge, a separate device-protected key, identity-bound authenticated
data and bounded ciphertext/index files. ZIP passwords and decoded configuration
are not stored in this cache. Unlocking imports the retained ZIP as session-only,
checks the connection identity, then resumes the requested action. Existing
session imports without a retained archive need one fresh selection. Forgetting
credentials destroys the cache key before removing the retained files.

Documents groups open sessions by format, ahead of recent closed documents. New/Open commands use a compact toolbar rather than tool cards. Private provider
sessions remain transient and recent history admits only ordinary provider UUIDs.
Workspace saving also checks that provider allowlist independently of the transient
flag. PrivateSessions records the opening client/generation; Home, document cards
and activation reject locked or superseded private sessions without consulting the
bridge during rendering. Private previews remain memory-only. Explicit ordinary
local downloads/imports retain their existing local-file semantics.

Drawer taps render cached menu contents immediately, defer credential/provider
queries to a worker, and do not checkpoint an editor just to reveal its menu.
Preparing a retained view invalidates the layout cache; every render rebinds its
native header. Connection-query failures are reported without stranding the next
refresh. The initial Chat selection mounts its lazy root without calling
Routes.show/host.activate from inside the native selection callback.

The app-owned UIButton subclass limits plain text buttons horizontally to their
public title/image rectangles and preserves vertical touch clearance. Visible
list rows, bounded glass buttons and compact icon controls keep their native
bounds. Actions fire on release inside, allowing ordinary scroll cancellation.

Validation: 191 mobile host tests; 53 portable mobile tests with three expected
platform skips; native bridge Go tests; lint and whitespace checks. Targeted iOS
26.5 simulator probes verified first Chat selection, 20 drawer toggles, a 402-point
plain button rejecting blank-edge hits and accepting its text center, Credential
label spacing and an opened Markdown document nested beneath its launcher actions.
Sources/screenshots/results are in the ignored Mobile/logs/credential-followup/
folder. These targeted checks do not constitute a full Android or native-suite run.

## Native first-selection ordering

`install_apple_selection` replaces the iOS OptionContainer selection handler with
an app-owned queued handler. Toga 0.5.7's `tabBar:didSelectItem:` may run before
UIKit updates `selectedViewController`; reading current_tab inside that signal
can therefore rebuild the previous destination. The queued handler reads the
settled selection, lets the host commit state, lays out the native controller,
and reflows the workspace/header. Programmatic selections remain synchronous;
their guarded signals cancel stale queued user events. This keeps the shared
commonUtils adapter unchanged.

The targeted iOS probe signals the native item before changing selectedIndex,
then verifies the first Documents frame, toolbar target and drawer action.
This covers event ordering that programmatic `current_tab` tests missed.


## LocalCrypt picker identity on iOS

The pinned Toga backend did not reload UIPickerView's row count before selecting
an item in a replaced source. Its text field could display LocalCrypt while
`Selection.value` still returned the first row, Local files. The app-owned
appearance adapter now reloads the picker immediately before native select_item,
keeping the displayed label and provider identity aligned. Private-open failures
are also copied to the visible browser status. Native LocalCrypt coverage opens a
synthetic encrypted CBZ through a fresh scoped browser and verifies its first page;
it does not import plaintext into the ordinary library or document store.


INI support is separately enabled in the private memory reader, stream-to-text
path, text chooser and native encrypted-write extension check. The 1 MiB text
limit and lossless TextSession encoding/line-ending behavior are unchanged.
The portable smoke fixture allowlist includes the new INI regression.

Validation: 213 mobile host tests; 54 portable tests with three expected platform
skips; native bridge Go tests including encrypted INI round-trip; lint/whitespace
checks. The targeted iOS 26.5 probe opened a real encrypted fixture CBZ through
CryptFiles/ManagedCopies, verified its decoded first image and correct storage
selection, then opened an INI in the private text view. Native INI saving is
covered by the Go round-trip and host UI save tests; the targeted simulator used
its existing executable for the open/display checks. Source/results/screenshots
are retained in ignored `Mobile/logs/localcrypt-open-review/`. Android rendering
and a full native suite were not exercised in this follow-up.


ManagedCopies retries a native archive unlock that requires configuration by
calling CryptFiles.archive_password. That provider walks logical ancestors only
within its root, reads each virtual remoteConfig.ini with a 64 KiB bound and
uses services.zip_passwords.password_from_ini for the desktop inheritance policy.
Plain archives do not require configuration reads. Explicit input is not silently
overridden. Parsing errors are sanitized and resolved values are never copied to
preferences, workspace history or diagnostics. A native fixture verifies this
path on a protected archive without an interactive entry step.

The iOS-only `show_legacy` preference defaults to false. FolderHubUI owns a
session override; the Settings switch refreshes retained browsers, the hub and
library shortcuts immediately without writing preferences. Explicit save
persists it; reload discards the override. FileBrowser filters logical directory
components before pagination, including search results and provider remote roots,
so LocalCrypt uses decoded names. The filter changes presentation only.

Credential group and retained-ZIP chooser labels share the iOS session visibility
policy, matching the `Legacy` prefix without requiring a dash. Filter presentation
without modifying package associations or retained credential data. When a selected
credential becomes hidden, both the selection and its retained name reset to All.


## Task-focused presentation (local UX passes, 2026-10-15)

`HubUI` renders visible open sessions before ordinary recent identities. Recent
reopening uses the existing checkpoint and reader/editor activation contracts;
private session titles and previews remain excluded. Card grids reflow to one,
two or three columns, including spacers for an incomplete row. Home reflows
Recent and Your spaces independently of the document grids.

Folder row activation enters the existing guarded browser directly. Its adjacent
action button retains the explicit copy/transfer route. Preparing this route
without presenting it provides a status and credential-resume owner; failed
browsing with a status can present the action route. No transient action screen
is added to the successful browse Back stack.

`appearance.reserve_navigation` applies measured floating UIKit tab-bar overlap
to the active ordinary view, preserving its original bottom margin. It runs from
workspace rendering and skips Chat and reading frames because those own their
clearance/chrome. It subtracts the container's existing safe-area inset before
measuring overlap. Split bar items are mounted only when a wide editable
workspace can use them. FileDrawer has one parent-folder control and a breadcrumb;
the inherited browser-history Back button remains available to code but is not
mounted in Local/LocalCrypt or Remote browsing. Native route Back stays intact.

Editor status comes from the document owner: durable recovery, source save,
session-only draft and conflict are distinct. A conflict exposes the existing
Save a copy command through `ActionMenu`, preserving owner rebinding and close
guards. No save, transfer, credential or persistence contract was changed.

Android retained destination roots are explicitly sized from the outer native
allocation, subtracting rail width when present. Measuring the child content
view instead is self-referential and can shrink the workspace on repeated
layouts. A host regression covers repeated renders and rail allocation; the
native phone probe checks 411 logical points of body width against the 411-point
window. Android's action bar follows the same light/dark surface palette.
