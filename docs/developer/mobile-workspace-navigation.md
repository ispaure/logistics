# Mobile workspace drawers and paired documents

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

The `files` destination key remains stable for routing and session origins; its
visible name is **Folder Hub**, with the desktop three-row hub glyph in navigation
and on Home. Its root lists logical folders. Selecting a row opens
`folder-options`; Browse Local/LocalCrypt/Remote then opens the corresponding file
browser. Pull/Push remain on the folder action page. Browser return links and the
drawer’s folder-management shortcut are labelled Folder Hub. The Documents drawer offers browse roots, recent identities, discovered libraries
and creation shortcuts. Browse roots and libraries mount the independent file browser
in the main route. The Folder Hub drawer implementation remains available, but its
hamburger is not mounted.


## Mobile feedback follow-up (2026-10-15)

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
