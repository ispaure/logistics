# Mobile UI refresh — local development

The user requested implementation of the reviewed UI improvements, with Transfers
last to avoid overlap with rclone work. All changes remain local; no commits,
pushes, tags or releases were made for this refresh.

## Implemented presentation

- Local file rows open on tap. Search is always visible; sort/view controls are
  secondary. Item menus select the correct resource without triggering an open.
  Metadata/cover work remains in the bounded commonUtils browser, with Details
  presented separately. New folder, rename, move and password entry use focused
  routes. The shared browser repository was not modified.
- Home uses compact workspaces and Continue; Documents lists sessions rather than
  repeating large launch cards. Labels and native menus retain the existing
  session-owned commands and close guards.
- Catalog views show searchable, tappable library records and saved position;
  reader commands move to Contents, Appearance and native menus.
- Ordinary and provider editors use compact chrome. Provider Markdown previews
  preserve the text buffer, reject navigation through the offline renderer, and
  clear HTML on navigation, suspension or private close/lock.
- Lists use vertical-only scrolling. UIKit line icons and surfaces use dynamic
  semantic colours. Filename buttons can shrink their intrinsic width without
  losing the full accessibility label. iPhones request tab-bar mode; iPads keep
  sidebar support. A wrapped zero-height UIKit content frame is repaired from
  its navigation controller before layout.
- Transfer status strips are unique to each view and registered through weak
  references. They show pending activity/completion without rebinding an editor,
  link to transfer details, and dismiss after completion. Progress animations
  only change mode when necessary. The existing Push review and Sync engine
  remain authoritative; folder cards move deletion/mapping actions into menus.

## Integration fixes

Briefcase packages named sources rather than arbitrary payload-root files. The
existing INI is copied into the packaged services directory and used as the mobile
fallback, retaining desktop exclusions rather than duplicating defaults. Native
fixtures now seed an actual encrypted folder rather than expecting a loaded
remote to create phantom storage. The delayed-transfer fixture blocks the current
mirror_sync operation. Navigation cleanup checks dispose the temporary proof
hierarchy while allowing a legitimate Home rebuild on restoring a tab.

Local folder enumeration uses a separate Python worker while a mirror pull is
running. It preserves the transfer cancellation handle and cloud-busy state;
remote engine operations remain serialized. Returning to Files selects local
storage during a transfer. Cached browser callbacks avoid remote thumbnail work
in this state. Native and host held-pull regressions cover entering folders,
returning to Files and preserving a writer draft.

Reparented browser subtrees receive a fresh scroll-content Box. The pinned layout
engine clears descendant roots and retains the old parent's layout origin when a
subtree is detached. A new parent rebases both through public widget APIs. Native
phone checks assert search and sort stay inside the actual scroll viewport.

## WebP comic pages

The mobile archive filters now include `.webp`, matching desktop page discovery.
The header guard accepts static VP8, VP8L and VP8X images and applies the existing
8 MiB, 8,192-pixel-per-axis and 16-megapixel bounds before native image decoding.
Animated WebP is rejected explicitly. iOS and Android decode page bytes directly;
no full-resolution PNG conversion or extracted page files are created. The same
page guard and format selection apply to ordinary and private readers. EPUB
illustrations retain their resource budget and use the correct WebP MIME type.

The native cover/thumbnail decoder registers `golang.org/x/image/webp` at pinned
v0.47.0; thumbnails remain bounded PNG output in memory. This version includes the
WebP dimension mismatch fix introduced in v0.43.0. Mixed-format natural ordering,
bookmarks, original archive preservation and private RAM-only reads are covered
by portable tests; native workflows exercise lossy, lossless and transparent
pages at original dimensions, with compiled thumbnail decoding tested separately.

## Verification scope

The frozen source is `/private/tmp/logistics-ui-refresh-snapshot`, based on alpha
`6f954a1` plus local UI, audit and rclone changes. The native bridge is rebuilt from
that snapshot, rather than reusing an older binary with newer Python modules.
The final snapshot includes the completed concurrent crypt-sync progress changes.

Host tests: 100 passing. Portable core: 39 passing. All 25 native cases and the actual workflow review passed on each of iPhone,
Android and iPad. The workflow includes lossy, lossless and transparent WebP
pages, native cover callbacks, editor headings and viewport bounds. Screens are generated inside disposable
synthetic test workspaces and contain no user documents or credentials.

Actual UI screenshots now accompany the native regression suite. The earlier
navigation-only screenshots were synthetic controller proofs and did not prove
real feature-screen usability. The actual workflow review runs after all 25 native regression cases,
including the held-pull local folder regression.

Physical provider permissions, touch gestures, hardware keyboards, screen readers,
large text/RTL and the complete OS/device matrix remain unverified. The Duo beta
simulator produced zero-height content frames; conventional phone verification
is recorded separately and is not a substitute for Duo/fold pose coverage.


## Final local evidence (2026-10-14)

The three native reports identify the same source snapshot:
`ce5fb42d80609a4113cb70dec5fc0c644b6b55f031a5130dbd9d849151344f8b`.
The bridge unit suite passed before rebuilding both platforms; host UI checks
passed 100 tests and the portable document suite passed 39 without skips.

- [iPhone native report](mobile-evidence/2026-10-14-ui-refresh-iphone-native-ui-local.json)
- [Android native report](mobile-evidence/2026-10-14-ui-refresh-android-native-ui-local.json)
- [iPad native report](mobile-evidence/2026-10-14-ui-refresh-ipad-native-ui-local.json)
- [Portable core report](mobile-evidence/2026-10-14-ui-refresh-host-core-local.json)

Actual synthetic-workspace screenshots are retained locally under
`Mobile/logs/ui-refresh/phone/` and `Mobile/logs/ui-refresh/ipad/`. They are local
review artifacts rather than publication of user content. The refreshed build
was installed and launched on the configured physical iPhone over localNetwork;
all 57 packaged runtime modules and the source stamp match this verified snapshot.
Physical installation/launch does not claim manual touch or accessibility testing.
No commits, pushes, release tags or store submissions were made.


## Local opening during transfers (follow-up)

`FilesUI.read_managed_file` allows a LocalFiles selection during a managed
transfer. Ordinary comic/EPUB imports run in the existing library path without
changing the cloud-busy flag. A navigation-generation check prevents a completed
import from taking over a newer view; the imported resource is still remembered.
Local text opens retain the provider-backed editor and verified source-save
contract. LocalTextCopies advertises offline access only for LocalFiles, so this
exception does not grant concurrent native crypt access.

PrivateController construction no longer clears the app's transfer cancellation
handle. An independent local open owns its worker cancellation event, skips global
busy-state changes and retires only its own session on failure. Already-open local
text sessions can be resumed or closed while a transfer runs. In-memory Markdown
preview is also available during a transfer. Existing remote/crypt operations and
save guards retain their serialization rules.

Host and native held-pull regressions tap text and comic rows, change comic pages,
reopen an unsaved text draft, and verify the source bytes, live transfer state and
original cancellation handle throughout. Two device builds are requested for this
follow-up; the first was installed before the fix, with launch blocked by iOS
because the phone was locked.


Follow-up verification: all 100 mobile host tests passed. The 25 native cases plus
actual workflows passed on both iPhone and Android at source snapshot
`1a149d9c50e22ef50a5b80fcc0eac0fab91e9ff2fb2dac02957d1a86a13d32d0`.
A further malformed-local-text test confirms a failed open removes its temporary
session, retains the existing draft and preserves the pull cancellation handle.

- [iPhone local-open report](mobile-evidence/2026-10-14-local-open-iphone-native-ui-local.json)
- [Android local-open report](mobile-evidence/2026-10-14-local-open-android-native-ui-local.json)

The second signed physical-device build matches all 57 current runtime modules.
Its deployment initially could not reach the iPhone because wireless transport
was unavailable; the later comic refinement build supersedes that pending build and was installed
and launched after reconnection.


## Comic reader space and gestures

Ordinary and private comic readers start with reading controls removed and zero
outer page margins. A native single tap on ComicCanvas restores controls; tapping
again hides them. EPUB keeps its existing explicit Restore controls button.
Navigation visibility belongs to the active view, with previous UIKit/Android
values restored when controls reappear or another destination is presented.
UIKit 18+ uses UITabBarController.setTabBarHidden:animated:; older runtimes use
UIView hiding. Native safe areas remain in effect.

Comic swipes turn pages only at fit scale, reverse for manga and ignore requests
beyond the first/last page. A queued swipe cannot enqueue another page operation
before it finishes. Android claims the gesture from its parent, uses a bounded
horizontal-distance threshold and excludes multi-pointer gestures from both
paging and tap actions. Zoomed gestures pan instead. UIKit keeps edge gestures
for system navigation and makes its scroll-pan recognizer wait for page swipes.

Verification includes 101 passing host tests, native zoom/fit/swipe dispatch and
measured image viewport growth when controls hide. Android checks deliver actual
MotionEvent down/up events; iOS checks exercise native recognizer delegates and
swipe target dispatch. These are automated gesture checks, not a claim of manual
physical-touch testing. Actual phone screenshots are retained under
Mobile/logs/ui-refresh/phone/ui-review-comic-{page,controls}.png.


Final comic refinement evidence uses source snapshot
`76b77558e89cb6ef7d7c43d60427cb4c65d448a83472be7330e1b87fc3b5fb03`:

- [iPhone comic focus](mobile-evidence/2026-10-14-comic-focus-iphone-native-ui-local.json)
- [Android comic focus](mobile-evidence/2026-10-14-comic-focus-android-native-ui-local.json)
- [iPad comic focus](mobile-evidence/2026-10-14-comic-focus-ipad-native-ui-local.json)

All three passed the 25 native regression cases plus actual workflow review.
UIKit assertions verify that the tab bar is hidden while page controls are hidden
and visible again after a page tap. Image viewport height increases in comic mode.
A delayed Documents selection now retains the active adaptive detail pane, and
nonanimated primary-root layout callbacks no longer dismiss a visible secondary
reader. Explicit list presentation and animated Back retain their existing roles.
The local iPhone build matches all 57 runtime modules in this snapshot.

The final comic refinement build was installed and launched on the configured
iPhone over localNetwork. It includes the local-opening-during-pull fix. Source
changes remain local; no commits, pushes or releases were made.


## Home Browse files re-entry

Home Browse files now calls show_home_files rather than the Locations hub. It
initializes cloud controls without waiting for credentials and requests a fresh
Local files root. Cached browser re-entry clears its search/history and refreshes
rows; a closed browser is rebuilt. Available storage choices refresh when the
engine is idle, retaining a valid previous selection and falling back to Local
files when an old crypt location is unavailable. Local listing is independent
while any cloud operation is busy, without changing that operation's busy flag
or cancellation handle. Native engine previews remain suppressed in this state.

The host regression presses the actual Home action after editor, Settings and
Documents views, with a stale folder/search, newly added files and a pending cloud
request. All 102 host tests pass. Native regression loops return from Settings,
Documents and Remote files; iOS verifies the Browse button wins UIWindow hit
testing before dispatching Toga's registered UIControlEventTouchDown. Android
uses native performClick. Both pass their 25-case suites and actual workflows.

- [iPhone Home Browse report](mobile-evidence/2026-10-14-home-browse-iphone-native-ui-local.json)
- [Android Home Browse report](mobile-evidence/2026-10-14-home-browse-android-native-ui-local.json)

The report fingerprints differ only in the iOS-only test-event correction;
the runtime implementation is identical between the two tested snapshots.

The signed local iPhone build matches all 57 runtime modules in the verified
Home Browse implementation. The first installation attempt failed because
CoreDevice reported that the phone disconnected immediately after connecting.
Installation is not claimed without a successful device response.

The retry successfully installed the Home Browse update on the configured iPhone
over localNetwork. Launch was blocked by iOS because the phone was locked.
All changes remain local, with no commits, pushes or releases.

## Folder selector and native transfer confirmations (local follow-up)

Files now starts with a native Selection containing discovered Local directories,
existing LocalCrypt copies and loaded remote roots/folders. Source labels remain
distinct even when names match. A focused folder-options route provides Browse,
and Pull/Push for mapped copies. Remote Pull uses the selected remote path; Push
uses the managed-copy review. Toga Selection items are ListSource rows, so remote
discovery explicitly reads row.value. Home Browse re-enters this picker; Local /
All files browsing still clears old search/location state without waiting for a
remote request. This supersedes the earlier direct-root Home shortcut.

Picker construction during startup does not initialize connection workers.
Secondary windows retain their existing original-window boundary. Local actions
remain usable while the serialized remote engine is busy.

Every mirror Pull write (new or mapped copy) and reviewed Push write passes through
confirmed_mirror_work with a native Toga ConfirmDialog. Cancel performs no work.
The dialog captures the client generation and mapping/plan identity, checks them
again after approval, and prevents overlapping confirmation requests. Read-only
Push planning stays separate. The iOS native UI review presents and captures an
actual UIAlertController with OK/Cancel, then dismisses the synthetic example.
Host tests exercise cancelled/accepted Pull and Push, changed connections, and
new-destination cancellation without creating a mapping.

Validation: 104 host checks and 25 native cases on each of iPhone iOS 27.0
and Android API 35 passed against staged source
`cdb470681cee22f50c083539dec4c684b5b6fbe19f603b839796e0567bcc5d39`.
The signed physical iPhone build contains the same 57 runtime modules byte for
byte. Evidence: [iPhone](mobile-evidence/2026-10-14-folder-picker-iphone-native-ui-local.json)
and [Android](mobile-evidence/2026-10-14-folder-picker-android-native-ui-local.json).

## Folder switching and iOS/Android parity assessment

The name-only Files selector now groups available copies under their logical
folder name, with a managed local copy preferred for normal Browse and mapped
Pull/Push. Alternate copies have explicit Browse actions. A local folder matching
a loaded remote can start a first Pull to associate storage. Delete local is on
the selected folder page, with native confirmation and inventory-checked deletion;
All files has no deletion command. Active transfers block deletion.

Entering Files from native destination selection rebuilds its root and clears the
old Files detail stack, preventing retained browser pages from becoming a different
root list. Folder discovery caches encrypted aliases while the engine is busy,
then refreshes them when idle. Action readiness updates when busy state changes.
Selecting an encrypted/remote folder during a pull is safe, but engine-dependent
browsing is disabled until completion; ordinary local navigation/opening remains
independent and preserves the live cancellation event.

UIKit Selection is a text field backed by a picker wheel. Its field resigns first
responder before folder navigation. The storage-selection change handler evaluates
programmatic-change guards synchronously, because an asynchronous handler can run
after those guards have cleared and revert an intentional encrypted-folder switch.
Blocked user switches restore the loaded source when still present, keeping rows
and provider identity aligned. Cleared selections do not restore absent entries.

The shared browser engine remains in commonUtils; Logistics owns row presentation.
Folder rows have one icon/name line and a chevron, without a repeated Folder label
or the transient selection checkmark before navigation. Files show compact size
metadata and contextual actions. Android now left-aligns and truncates long row
titles, matching iOS behavior while retaining native OS controls.

The portable BrowseTree contract accepts opaque identities and arbitrary payloads.
A host test exercises JSON-like folder identities and archive-member payloads
without disk paths. This validates reusable presentation/navigation; it does not
claim a new end-user archive explorer or JSON importer. Those need source adapters
and their own access/write policies. Local, CryptFiles and remote adapters already
use this presentation.

Parity scope: both native suites exercise background Pull with selector switching
and local text/comic opening, encrypted file mutations, mapped Push confirmation,
compact row layout, and return-to-Files navigation. UIKit verifies an actually
focused picker closes on selection. Both OS confirmation implementations are
presented; Android clicks its native Cancel button. UIKit captures its native
OK/Cancel alert and dismisses the synthetic example. OS-specific differences
remain intentional: native menus/dialog styling and tablet scene ownership.
Physical gestures and screen-reader behavior still require manual device evidence.

Validation: 108 host checks and all 25 native cases on each platform passed
against source `7ebcadd1b8a15e926dcd2f8d78a7d17bb3f03b1e536e84774b9677853f321715`.
Evidence: [iPhone](mobile-evidence/2026-10-14-folder-parity-iphone-native-ui-local.json)
and [Android](mobile-evidence/2026-10-14-folder-parity-android-native-ui-local.json).
The signed local iPhone build matches all 57 runtime modules byte for byte.

The log audit also caught Android Spinner's transient stale index when its source
is cleared. Storage-selection callbacks now ignore that transition and evaluate
programmatic guards before reading the native index. A focused host regression
exercises the IndexError path. Root selectors refresh in place after credential
restore, so opening Files before restore completes does not leave a local-only
list. Both normal and independent-local listings check the requested source and
location before publishing results; a delayed older listing cannot overwrite a
newer folder. A host regression explicitly interleaves those results.

Final signed build installed and launched on the configured physical iPhone over
USB, with its bundle/team/device identity preserved. Both final native logs were
checked for handler exceptions; none were present. No commits or pushes were made.

## Dark-mode follow-up and final parity validation

`appearance.py` isolates compatibility fixes for the pinned Toga 0.5.7 backends.
It uses UIKit's semantic label/input/caret colours for default styles, including
multiline placeholders. Explicit non-default foreground colours are preserved.
The Android generated app now inherits Material DayNight and declares uiMode in
its existing configuration-change flags. Application configuration callbacks
refresh live text, selector, input, background and navigation colours without
replacing the activity or touching document/transfer state. This follows the
[Android dark-theme contract](https://developer.android.com/develop/ui/views/theming/darktheme).
Small selected navigation labels retain their theme hue while meeting 4.5:1
contrast against the surface. Markdown/EPUB CSS explicitly pairs CanvasText with
Canvas and preserves offline content policy and reader theme preferences.

Android button hints now allow flex rows to shrink without making ordinary
Back/Sort captions unreadable. List rows keep flat surfaces and normal title case;
native ellipsis and touch targets remain. The native review checks browser controls
against the actual viewport and verifies non-truncated toolbar captions.
Picker arrows and input outlines receive theme-aware tinting.

Screenshot review exposed both the clipped Android controls and empty exported
artifacts after emulator shutdown. Android captures now write verified PNG bytes
and fsync the file before the disposable emulator exits. Actual light/dark images
were retrieved and visually reviewed for ordinary/provider editors, Markdown,
Home, Files and Settings. Test images contain only synthetic fixtures.

All 117 mobile host tests and 25 native cases on each platform passed. Native
checks cover light/dark editor colour/contrast, selected navigation text contrast,
OS theme changes preserving drafts and the Android activity, picker dismissal,
background local browsing/reading, and encrypted file operations. Final source:
`9fc2005af0ff39f3999436554d1529f7502f79e9ac3a73fb057e6af7cbe06015`.
[iPhone report](mobile-evidence/2026-10-14-dark-mode-iphone-native-ui-local.json) and
[Android report](mobile-evidence/2026-10-14-dark-mode-android-native-ui-local.json).
The signed iPhone app matches all 58 staged runtime modules byte for byte.

The final build was installed and launched on the configured physical iPhone over
the local network. Both light and dark editor images, and final unclipped Android
file rows, were visually reviewed. Temporary inspection emulators were closed.
All requested changes remain uncommitted and unpushed.

## Comic re-entry and Local/LocalCrypt audit

The UIKit comic scroll view now opts out of automatic navigation-bar insets,
uses symmetric letterboxing insets and restores the fit-page offset on every
layout, including unchanged bounds. Zoomed content remains pannable. Native
checks measure the page centre after repeated Settings/reader round trips and
control/fullscreen transitions, for ordinary and encrypted comics on both
platforms. Android already centres through its image matrix and needs no new
backend branch for this correction.

Files, Move and editor Open/Save As use the same storage-provider resolver.
Already constructed pulled providers retain their namespace. The local-open
bypass during Pull explicitly excludes private providers: CryptFiles inherits
LocalFiles and cannot be classified by that superclass alone. Private bookmark
controls now retain up to 200 page/chapter positions per open session, with no
workspace/recovery record, and clear them on close.

| Operation | Local | LocalCrypt |
| --- | --- | --- |
| Browse hierarchy, search, sort, list/tiles, details and bounded previews | Shared browser | Shared browser over decoded names |
| Create, rename, move, confirmed delete | Shared resource operations | Same operations over encrypted storage |
| Text/Markdown open, edit, preview, verified Save and Save As | Local file publication | Encrypted publication; cross-storage move/save remains explicit |
| Comic WebP pages, fit, zoom, swipe, fullscreen | Native comic canvas | Same canvas |
| Pull, reviewed Push and Delete local | Mapped folder actions | Same actions; ciphertext-preserving transfer and credential checks |
| Browse/open while Pull occupies the engine | Unrelated readable local files remain usable | Engine-dependent decoding waits |
| Pins, restore and reading state | Local pins and library progress/bookmarks can persist | Decrypted locations and bookmarks stay in memory |
| EPUB presentation | Sanitized formatted chapters and appearance controls | Chapter text in the private reader |
| Archive metadata editing | Details display metadata; ordinary library reader has no edit command | Private reader exposes encrypted metadata editing |

The last two rows remain reader differences, not folder-provider feature parity.
Rich private EPUB rendering needs a deliberate WebView/cache privacy contract;
ordinary metadata editing needs a clear decision about editing the original
Local file versus its imported library copy. Neither should be silently routed
through the other storage mode. Browser ownership and the proposed optional
backend entry point are described in [shared ownership](commonutils-integration.md#mobile-browser-boundary).

Validation: 118 host tests and 26 native cases on each of iPhone and Android,
with no native handler/task exceptions. Both native reports and the signed
physical iPhone app use source stamp
`dd5ce03b275ced139af4cf1d0eb1257b0394f1988fda8ac1e62c3f80a6e960b1`.
Evidence: [iPhone](mobile-evidence/2026-10-14-comic-reentry-iphone-native-ui-local.json)
and [Android](mobile-evidence/2026-10-14-comic-reentry-android-native-ui-local.json).
These are local validation results, not a published release.

The matching signed build was installed and launched on the pinned test iPhone
over localNetwork. No commit, push or release publication was performed.

## Physical iPhone screen-level centering correction

The earlier centering assertion compared the page only with its own widget.
An actual iPhone screenshot showed the remaining displacement. An opt-in
on-device check reproduced a fullscreen viewport shrinking from 839 points to
590 after controls were shown and hidden, then returning at 756 points after
reopening. The image was centred inside that shortened viewport.

The outer UIKit host now fills its native navigation area without subtracting
safe areas that the leaf controllers already apply. Leaf roots are repaired
from their navigation host bounds on layout, including nonzero stale frames.
Fullscreen chrome is reconciled when moving between readers. Android observes
the content viewport's layout events even when its navigation bar is GONE, and
hides/restores the native title bar with immersive comics. Transfer notification
banners are suppressed while a comic requests fullscreen and return with its
controls; bridge work, cancellation and notification state remain intact.

Native assertions now compare with the independent workspace/screen safe area
and require the fullscreen viewport height to stay stable across transitions.
The encrypted reader regression runs after completed transfers, catching the
otherwise invisible 44-point notification strip that displaced those pages.

`LOGISTICS_COMIC_LAYOUT_CHECK=1` is an explicit iOS developer launch opt-in. It
opens an existing ordinary library comic, toggles controls and Settings/reader
round trips three times, and writes window screenshots plus geometry to the
app cache's `logistics-comic-layout` directory. Normal launches do not run this
check or capture screenshots. It does not rewrite comic content. User-content
screenshots are retained locally rather than added to public evidence files.

Final validation: 126 host tests and 26 native cases on each of iPhone, Android
and iPad passed. Native logs contain no callback/task exceptions. All native
reports and the signed, installed physical iPhone build match source stamp
`e739b5e3aa817b17e3f02c985a87c7ebc0b4b3c2bf33865596bee198b1b3aba6`.
The actual iPhone completed three controls/fullscreen and Settings/reader cycles
with ten captured states, including seven fullscreen states: every fullscreen
viewport was 839 points high and the maximum error against the window's usable
vertical centre was 0.042 points. Screenshots were visually inspected; an iOS
device screen capture independently confirmed the final visible state.

Evidence: [physical iPhone geometry](mobile-evidence/2026-10-14-comic-screen-physical-iphone.json),
[iPhone native suite](mobile-evidence/2026-10-14-comic-screen-iphone-native-ui-local.json),
[Android native suite](mobile-evidence/2026-10-14-comic-screen-android-native-ui-local.json),
and [iPad native suite](mobile-evidence/2026-10-14-comic-screen-ipad-native-ui-local.json).
The build was installed and launched over localNetwork. Changes remain local;
no commit, push or release publication was performed.

## Back from files to the browser

Browser-opened ordinary comics/EPUBs and Local/LocalCrypt provider documents
are presented in the Files navigation stack rather than forcing Documents.
The session controller carries a runtime `presentation_destination`; an
explicit Open documents activation resets that destination to Documents.
Session ownership, resource identity and persistence policy remain unchanged.
Native pop reveals the existing browser panel, without listing again or
recreating its tree. Back keeps open sessions and drafts, and applies hidden
private preview/image cleanup when the file listing becomes visible.

Reader-manager catalogue initialization can now build without presenting the
Books & Comics page, avoiding an intermediate catalogue/tab change during file
import. Fullscreen chrome follows the reader's actual destination navigation
controller; Files-origin readers no longer hide the unrelated Documents bar.

The native browser Back fixture opens a comic, a text draft, and the cached
comic again from a nested folder. It invokes UIKit navigation pop and Android's
Back dispatcher, then checks folder, tree identity, settled scroll offset and
retained sessions/drafts. The host fixture also checks retained search and
explicit activation through Open documents.

Validation for this change: 128 host tests and all 26 native cases on each of
iPhone and Android passed, including actual native Back, retained browser scroll,
and an unsaved text draft. The native reports and signed physical-device build
match source stamp
`36a2f4f3e73915571bf24c444ce1637db68de1ccba9425d468310d7f189cb30b`.
Every shipped Python source was compared with the validated frozen payload.
The frozen payload uses the previously tested commonUtils revision; ongoing
shared-repository edits were not included in this device build. It was installed
and launched on the paired iPhone over localNetwork, preserving app identity and
data. This also includes the generic `Remote:`/`Remote:subfolder` display fix.

Evidence: [iPhone native checks](mobile-evidence/2026-10-14-browser-back-iphone-native-ui-local.json)
and [Android native checks](mobile-evidence/2026-10-14-browser-back-android-native-ui-local.json).
Changes remain local; no commit or push was performed.

## Mobile architecture cleanup

Reader controllers now use the enumerated services in `reader_host.py`. Their
mutable document fields and operation cancellation stay with the controller;
`Readers` and `PrivateSessions` no longer publish document fields onto the app.
Session tokens, private retention limits and scene writer restrictions remain.
Reader tools/appearance have distinct routes, so Back returns through the reader
before revealing the retained origin browser. Provider busy/close guards and
cancel actions operate on the originating controller.

`reader_controls.py` supplies shared reading layout, page buttons and bounded
swipe scheduling; ordinary and provider adapters retain their own storage,
bookmarks and cleanup. `library_ui.py` owns the catalogue and `reader_ui.py` owns
reader workflow. Books/Comics mobile format presentation lives under the feature
owners. Generic image gestures, native navigation, route containment and chrome
restoration live in optional `commonUtils.ui.native`, together with Android
bridges. Native APIs/build requirements are documented in commonUtils.

Validation: 134 mobile host tests, 62 portable/packaging/feature core tests,
26 desktop EPUB reader tests, 20 desktop comic reader tests and three shared
component tests passed. The desktop comic browser initially hit a settling
timeout; the isolated case and full suite rerun passed. All 26 native cases on
each of iPhone, Android and iPad passed with source stamp
`c91ebe011850ffbd8012c2850ae8a8b1c97c5e67942a39c54829f26e7163aa31`.
Native logs contain no callback/task tracebacks. Added checks verify explicit
reader ownership, cancellation separate from transfers, tools Back returning
to the reader, and then Back preserving folder/scroll/drafts. Shared component
tests use a separate Toga consumer with Logistics/feature imports blocked;
packaging tests reject changed native Java during release staging and verify
that Java changes alter the local source fingerprint.

Evidence: [iPhone](mobile-evidence/2026-10-14-architecture-iphone-native-ui-local.json),
[Android](mobile-evidence/2026-10-14-architecture-android-native-ui-local.json),
and [iPad](mobile-evidence/2026-10-14-architecture-ipad-native-ui-local.json).
iPad also exercised supported independent windows. Physical Android interaction
was not tested. The selected shared baseline is revision `615a70d` plus this
cleanup; concurrent shared desktop/index work was excluded from the frozen build.

The matching physical iPhone build was signed in a fresh output directory. Every
shipped Python source matches the validated payload and obsolete Logistics
canvas/navigation/routing/rendering modules are absent. Installation over
localNetwork succeeded with the existing bundle/signing/keychain identity and
app data preserved. After unlock, the app launched successfully. The physical
iPhone completed three controls/fullscreen and Settings/reader round trips with
ten captured states. All seven fullscreen states retained an 839-point viewport;
maximum vertical centre error was 0.042 points. Initial, repeated and reopened
screenshots were inspected, and an independent device screen capture confirmed
the visible result. [Physical geometry](mobile-evidence/2026-10-14-architecture-physical-iphone.json)
records the result without user comic screenshots. The app was then relaunched
in normal mode with the diagnostic opt-in disabled.
No commit, push, TestFlight upload or release publication was performed.


### Local folder deletion (2026-10-14)

Local and LocalCrypt folder deletion presents confirmation before any recursive
inspection. After confirmation, a worker calls `MirrorJobs.wipe_folder` (or
`delete_copy` for mapped folders) to remove the entire tree with `shutil.rmtree`.
Files added while confirming are included. The operation has no entry-count limit,
content baseline, Trash fallback, backup, or app restore. Guards admit only named
folders under app-private LocalFiles/LocalCryptFolders, reject parent traversal
and linked target/ancestor paths, and nested symlinks are removed without following
their destinations. Active operations and private reader edits must finish first.

Mirror records now save schema 3 without snapshot lists. Legacy schema 1/2 records
remain readable, but pending backup journals cannot restore local trees. The
obsolete TransferSnapshots tree is removed in the worker during deletion or the
next transfer; snapshot browse actions are removed. Push review baselines remain
in use for remote mutation review. Regression tests cover immediate confirmation,
changes during confirmation, both local storage types, link boundaries, and legacy
backup removal across restart.

## Native screenshot capture

Native evidence captures the complete UIKit window or Android activity decor view,
including navigation containers. Toga's content-only screenshot can have zero bounds
while native navigation reparents content. Android capture waits for positive native
window bounds and still fails on empty/invalid PNG data; it does not skip screenshots.


## Explicit storage browsing and focused transfer details

The Files folder selector offers Transfers and Refresh. Connection management
is available through Settings → Remote connections…, without a Connections
shortcut on the selector.

Folder actions use the desktop storage names: Browse Local (on this device),
Browse LocalCrypt (encrypted on this device), and Browse Remote (online).
Discovery only contributes existing local directories and loaded remotes; the
folder page deduplicates copy references. Managed subfolder remote browsing uses
the mapping's prefix, decoding ciphertext paths with the matching connection
before browsing. Push/Pull remain folder actions. The online browser keeps
copy-to-device and secondary path/download/connection commands; its main view
no longer repeats the remote selector, Connections, or Push/Pull controls.

The `transfers` route is titled Transfer details and owns progress, cancellation,
pending review and results, without a mirror-job catalog. Ambiguous remote pulls
use a separate `transfer-copy` route limited to matching destinations. The legacy
remote push handler similarly resolves local copies before review. Remove mapping
(keep files) now belongs to the managed folder's action page. Transfer banners
continue to open details, and the remote browser receives the same progress. Long progress and result notices use the mobile
line-wrapping helper so their full text remains visible on narrow phones.


### Documents and Chat navigation cleanup

The mobile shell now has Home, Files, Documents, Chat and Settings destinations.
Chat owns its conversation root and settings route, independent of Documents’
adaptive list/detail presentation. Documents exposes New and Open, without
Library or Chat shortcuts. The book catalog remains available from Home and Files.
New presents a native format prompt for TXT or Markdown (both use the existing
text editor, with Markdown preview). Programmatic `new_document()` remains an
immediate creation command for imports, tests and internal callers.

`clear_unmodified_documents_on_restart` defaults to true. Before binding scene
owners, startup removes clean managed text sessions and reader sessions from the
restored workspace manifest. It preserves modified text, conflicts and entries
whose recovery records cannot be read. This only changes open session membership;
DocumentStore bytes, recovery records and book progress are retained. Startup
does not create an empty document or reopen an arbitrary stored file while the
setting is enabled. Disabling it retains the previous restore behavior.

The Documents hub groups both open sessions and stored text documents by type
(Text, Markdown, EPUB books, Comics), omitting empty groups. Open rows show the
filename and any recovery/conflict/session status; the type appears once in the
group heading. Stored grouping uses document metadata, preserving duplicate-name
labels and resource identities. Open summaries prefer live editor names, resolve
inactive text names/types from DocumentStore and reader names/types from library
records. Workspace manifests continue to omit names. Reading library metadata
does not open a decoder; unavailable records retain a selectable row and close
menu. Host regressions cover mixed groups, duplicate Markdown names, restored
text/book/comic names, recovery status and missing records.

### Optional document card overview

The mobile-owned `document_card_overview` preference defaults to true. Documents
uses two card columns on phones and three at widths of at least 1100; resize
reflows existing cards. Type grouping and stored-document lists remain intact.
Cards use bounded, plain-text excerpts from managed text only, including live
drafts. They do not capture screenshots, mount readers, decode books, or preview
private provider content. Reader/provider sessions use type placeholders. Titles
and resume actions retain session identities; close uses `request_close_session`
and its existing draft guard. Disabling the preference restores grouped rows.

Settings is vertically scrollable, with workspace preferences under App followed
by feature sections for Text & Markdown, Books & Comics, LM Chat and Files. Chat
configuration initializes lazily when entered from Settings; reader appearance
remains with its reader owner. The overview switch saves immediately and replaces
the retained Documents root even when detail routes are present; it preserves
navigation and draft owners. A failed save restores the switch and reports the
error. Save/reload preferences also refreshes the retained root. Host tests cover defaults, persistence,
list fallback, resizing, live draft previews, resume ownership and guarded close.

### Files folder list

The Files root now renders folder choices as direct, name-only list buttons in a
vertical scroll container. Transfers and Refresh remain above the scroll area.
Refresh uses the native circular-arrow image on iOS, the system sync drawable on
Android and a circular-arrow glyph on host backends. Folder taps open the existing
copy/action page; copy grouping, mapped scopes and busy-operation rules are retained.
Credential restore updates the visible list in place when Files is at its root.
Host checks cover top controls, scrolling structure, newly discovered folders,
late remote restoration and local browsing during a transfer. Native fixtures
now tap folder rows and check the refresh image; these updated native checks
have not yet been run on devices.

The iOS multiline-input appearance hook disables automatic scroll insets because
the navigation host already reserves keyboard and safe areas. On supported UIKit
versions it also hides top/bottom scroll-edge effects. A local iPhone simulator
probe reproduced obscured text with a 115-point adjusted bottom inset inside a
100-point editor, then verified zero adjusted inset and readable scrolling text
after the change, including dark appearance and repeated native `insertText`.
The format prompt and five-button bottom bar were also visually checked. These
focused checks do not constitute the full native release gate or physical-device
verification. The native UI review now checks the inset/edge contract and captures
an additional editor-typing screen.


Local validation for the explicit storage and transfer-details changes: 159 mobile
host tests passed, followed by all 26 native cases on iPhone, iPad and Android.
The transfer-result screenshot confirms complete wrapped text. The same source
snapshot was signed, installed in place and launched on the paired iPhone over
Wi-Fi. Local reports are retained under `Mobile/logs/explicit-storage-*-native-ui-local.json`
and `Mobile/logs/device-deployment.json`; these are local dirty-source checks,
not release or TestFlight evidence.

### Conversation-first Chat presentation

The approved mobile Chat design replaces the read-only text transcript with an
app-owned offline WebView. User turns are bubbles; assistant turns are full-width
basic Markdown with visible role/recovery status and a Copy action. The native
header contains the conversation title, model and native overflow commands.
The existing destination-owned conversation drawer and its pane allocation are
preserved. The native composer estimates wrapped lines and grows from 52 to 120
points. Its single Send button becomes Stop only during reply generation, and is
disabled during model refresh. Empty status containers occupy no message space.
Configuration uses a scrolling route and its own feedback widget.

`chat_presentation.py` owns pure formatting and layout estimates. It reuses the
inert `preview.markdown_body` parser (now including semantic numbered/bulleted
lists). Content is escaped, links remain inert, and the document CSP denies
external resources and page scripts. Python evaluates only app-owned rendering
code; message data enters that code through JSON. The transcript patches the
changed tail rather than reloading the page or reformatting every previous turn.
Unchanged message nodes retain selection. Streaming follows only near the bottom;
a Latest message button allows returning after scrolling up. A conversation
change or explicit Send follows the latest turn. Load generations and a single
coalescing render task prevent stale pending updates from owning a new document.
The native navigation host continues to own keyboard/safe-area sizing.

Validation for this chat change: seven focused dummy-backend UI checks plus seven
existing workspace checks passed; five pure presentation checks, three preference/
preview checks, two packaging checks and four existing chat persistence/transport
checks passed. A headless browser checked 320/390/768-pixel transcript widths,
light/dark appearance, inert hostile markup, zero resource requests, preserved
scroll position and Latest message behavior. These are host checks, not native
keyboard/device evidence. The native LM case now also waits for the rendered
reply and asserts message separation, viewport fit and the restored Send state;
that updated native case still needs a simulator/emulator run.


## Slate palette and menu touch targets (local follow-up)

`logisticsmobile.palette` owns Qt-free mobile roles based on desktop Slate's
current default colours, including the 6% blue tint on dark neutral surfaces.
Light cards use near-white `#fafbfc`; the window uses `#f0f2f6`. Mobile does not
import Qt or synchronize desktop custom theme preferences. `appearance` adapts
native colours and card strokes in Logistics without changing commonUtils.
UIKit text/background colours use dynamic providers; card CGColor strokes update
on trait changes. Android refreshes live widgets and card drawables on uiMode
changes without replacing the activity. Markdown, chat and sanitized EPUB pages
use the same roles; explicit reader Light/Dark still overrides device appearance.

Workspace bar menus use image/title UIBarButtonItems with the retained Toga
button as their action target, rather than mounting a Pack-constrained custom
view in UIKit's bar. UIKit owns their visible bounds and hit testing. Inline
hamburgers use TouchUpInside instead of TouchDown so a drag away cancels opening.
Native checks require no custom menu view and test palette colours separately
from platform labelColor defaults. Physical random-touch reports still need
confirmation on the user's device after rebuilding.


Validation for this follow-up: 172 mobile host tests passed; the portable mobile
suite passed 51 tests with its 3 platform-dependent skips. A dedicated iOS 27.0
simulator probe passed light/dark card, editor and retained-stroke checks, sampled
content hit testing, native bar geometry and inline TouchDown/TouchUpInside
cancellation. It used the existing simulator executable with current Python UI
sources; this is targeted evidence, not a new full native-suite/device-build
claim. Screenshots, the probe and source hashes are retained locally in
`Mobile/logs/palette-review/`. Android native rendering and physical touch
confirmation remain pending. No device installation, commit or release was made.
