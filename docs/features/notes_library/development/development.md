# Notes Library development

[Notes Library guides](../notes_library.md) · [Implementation brief](../../../development/notes-library-feature-brief.md)

| Change | Owner and focused tests |
| --- | --- |
| Model, containment, links and mutations | `Python/features/notes_library/notes.py`, `notes_links.py`, `library_files.py`; desktop/mobile Notes Library suites |
| Desktop session destination | `ui/page.py`, `desktop/documents.py`, `desktop/sidebar.py`; `test_notes_library_hosting.py` |
| Desktop documents and groups | `ui/notes_library.py`, `ui/document.py`, `ui/library_workspace.py`; `test_notes_library_desktop.py`, `test_notes_library_tabs.py` |
| In-library file previews | `services/documents/file_preview.py`, `ui/file_preview.py`, `mobile/file_preview.py`; desktop tabs and mobile Notes Library suites, native Notes Library probe |
| Mobile library | `mobile/notes_library.py`, library panels/tools/editors; mobile Notes Library and Markdown library workflow suites |
| Shared mobile authoring | `services/documents/authoring/`; mobile Markdown editor, provider and workflow suites |
| Feature state and payload | Desktop runtime preferences, mobile preferences/features, owning source manifests; feature-preference/mobile-feature and packaging tests |

## Destination and feature contract

The mobile and desktop library panels retain an interface per search scope.
Each owns its query control, result widgets, pagination and status; the existing
provider scanner remains shared. Scope switches cancel pending work and advance
its publication generation before restoring the target interface. Completed
queries are retained, while library mutations and saves invalidate cached queries.
Retirement clears both scopes, including hidden query controls. Mobile also keeps
Files rows separate from both search scopes.

The mobile `test_notes_library_modes.py` and `test_notes_library_panels.py` suites
and desktop `test_notes_library_desktop.py` cover independent inputs and results,
pagination, late callbacks, provider scope and retirement. The managed
`document_storage_tools ios|android --probe notes-search` check exercises retained
native inputs/results across scope changes and rotation using synthetic notes.

Sidebar navigation reuses the current inner document owner, preserving its
history and existing save/discard/cancel transition. Explicit `new_tab=True`
opens/focuses a separate document. Files without a Markdown/source/notebook
adapter use a memory-only `FilePreview` in the same library pane; images and
PDF pages use existing image validation and PDF backends. Other formats display
metadata without loading arbitrary binary data. Video previews retain a revocable
`VideoContent`/`VideoTransport` range stream, with desktop Play/Pause and seek
controls or a mobile HTML video element. Neither starts decoding until Play.
Markdown image and video embeds use the same authoritative lookup as file links:
current folder, library root, then a unique suffix match across the library.
Conventional attachment folders do not bypass ambiguity checks. LocalCrypt uses its
ciphertext-name search for these fallbacks. Link resolution accepts any
contained file, retaining hidden-path and library-root restrictions. File
previews retire rendered content, PDF bytes and video streams on replacement, close or lock;
page workers finish before their content is released.
File-preview creation also closes its stream if validation fails while leaving
the provider operation. A failed media resolution revalidates cached video
streams, retires deleted or revoked entries, and preserves the resolver's error
for the rendered placeholder. Standalone video embeds try decoded URL names
before their literal spelling, matching image and navigation fallbacks.
Each opening render passes its own cancellation predicate into media lookup;
the document's reusable media owner does not retain a cancelled render predicate.
Cancelled mobile PDF page tasks keep their busy state until the underlying
renderer finishes; retirement then closes its bytes. Page-render errors leave
the previous page selected and remain visible. Switching to an embedded file,
source editor or drawing retires the previous Markdown media and reader DOM.
Extensionless links prefer exact current-folder/root filenames before `.md`.

Desktop Markdown toolbars host the library-only Links toggle after the reader
controls. Each inner document owns its connections tree and worker, so panel
visibility and results follow that tab, including split groups. Non-Markdown
files hide the panel while retaining its toggle preference.
Background note loads refresh enabled panels, tab activation rescans saved
connections, and saves/library mutations refresh panels in other documents too.
Library layouts remove nested window margins and hide the alternate-format toolbar for Markdown.
Empty status lines collapse; messages use the shared File Browser `StatusLine`
height. `test_notes_library_tabs.py` checks tab-local backlinks, panel visibility,
edge geometry and compact idle footers alongside history and save lifetimes.

The November 2, 2026 file-opening validation covered desktop active-tab
replacement and cancelled draft navigation, image/PDF/information views, PDF
page changes, mobile in-library links and unchanged session routing, and payload
startup. The extended native Notes Library probe passed on disposable iPhone
and Android devices, including rendered image/PDF pages and return to Markdown;
their QA devices/apps were removed afterward. This does not certify physical
devices or every platform-supported file format.

`notes_library` registers a lazy page and folder actions independently of Text
Editor. Desktop `ui/page.py` reuses `DocumentsPage` workspace lifecycle with a
separate named document host and a distinct docking group. Library windows declare
`document_destination='notes_library'`; commonUtils routes presentation, creation
scope and close callbacks to that host. The rail reserves its layout immediately
after Documents. Home receives the registered page through the launch catalog.

The empty state opens an existing folder through the shared provider picker in
folder mode. An `.obsidian` marker is needed for automatic browser offers, not for
explicit folder selection. Identity uses normalized physical roots for ordinary
local storage and provider/credential context plus contained root for private
storage. Reopens focus a retained or detached session. Library sessions stay out
of Documents counts and its overlay; their inner document groups stay unchanged.

Disabling Notes Library removes new opens while retaining a reachable rail route
for open sessions. Closed empty disabled pages leave navigation. The feature
preference is seeded once from the former Text Editor state, then independent.
Mobile keeps its Documents destination and gates libraries separately from
standalone text/Markdown. Shared authoring lives in document services. Notebooks
and Rclone are optional integrations; local Markdown/source libraries require
neither feature. New drawing opens/creation require Notebooks enabled; retained
drawings keep their normal close/save lifecycle.

Use [the validation workflow](../../../development/testing.md). Source extraction
and host checks do not replace native interaction checks; record their scope
separately and keep raw evidence outside the wiki.

## Notes Library data views

Notes Library owns breadcrumb presentation for every embedded document kind.
Ancestor landing pages use the same bounded provider probes as sidebar folders,
including files opened before their ancestors are expanded. Probes run off the
UI thread; links follow the existing document navigation/save/history path.
Desktop places a horizontally scrollable rich-text path beside history. Mobile
keeps the filename in its title and places the complete folder breadcrumb between
history and edit/actions on the next row. Both preserve every ancestor and start
at the end of an overflowing path. `mobile/breadcrumbs.py` removes Toga's default
100-unit scroll-container minimum, allowing a 320-point row to retain its right
controls. It defers initial scrolling until native viewport/content measurements
agree with the current layout; retries are bounded and cancelled for obsolete
paths or disposal. Once positioned, ordinary user scrolling is left alone.
Folder breadcrumbs open a landing page when present, otherwise reveal the folder
in Files. Files retains its separate rule that only landing-page names are
underlined. Closing or locking the library clears the displayed path.

Apple and Android keep note history, edit/view and Note actions in the content
row beside breadcrumbs. Read-only libraries omit edit/view. Files and Links remain
in the title row; Android's native title bar reserves only the actual control
counts at its logical start/end. The content row follows the document pane, so
expanding Files does not place note commands over the file list.
The Apple content title reclaims the navigation strip only when the native bar
is vertical. Horizontal bars retain their full safe inset so native actions
cannot cover the title's Files and Links controls.

`python -m mobile_build.validation.document_storage_tools ios --probe notes-header` exercises
native note history and edit/view handlers, live action menus, header hit tests,
long titles and portrait/landscape rotation. `--family all` includes iPhone,
iPad and the Duo closed/open/partial postures with the reviewed `--duoctl`
helper. It uses isolated QA applications and disposable simulators.

Focused validation covers folder-note underlines, folder browsing, narrow/wide
ancestry, file-type transitions and history in desktop/mobile host suites. Native
iPhone simulator and Android emulator Notes Library probes also exercise folder
links for Markdown, images, source files and unsupported files, with screenshots
reviewed for narrow layouts. Both runners remove their QA app and disposable
device. This does not certify physical-device gestures or every tablet layout.

`notes.document_kind` and `DOCUMENTS` define filename-only routing for Markdown,
source text and notebook files. Provider listing and content search share this
supported-type boundary; hidden configuration stays excluded. Explicit links may
resolve to any supported document, while extensionless note links still mean `.md`.
Connection scans index supported file paths but read bodies only from Markdown.

Desktop `ui/library_text.py` embeds the shared `CodeEdit`, `SyntaxHighlighter` and
`SearchPanel` without creating an external editor window or a local-file recovery
session. `DocumentResource` owns the source baseline and verified provider writes;
the library retains Save-before-navigation/close and waits for editor/search work.
Mobile `mobile/library_text.py` owns the common text draft/read/save/retirement
lifecycle using the existing `CodeInput`; `LibraryMarkdown` adds formatted mode
through this base. Text and notebook opening use `VaultBrowser.open_embedded`
for one history, publication and cleanup path. Source-file saves preserve BOM,
encoding and line endings, and opening JSON/JavaScript never executes it.

`dataview.py` parses complete top-level `dataviewjs` fences, retains their source
spans and supplies per-render `ViewFiles` reads through `DocumentResource`.
Requests obey library containment, hidden-configuration exclusion, provider access
checks, cancellation and byte/request budgets. Each worker first requests a
render-local Markdown filename index with library-relative `file.path`,
`file.folder` and `file.name`, plus the calling note for `dv.current()`.
Workers request provider-reported byte sizes with this index for synchronous
`app.vault.getMarkdownFiles()` / `dv.app.vault` compatibility. This metadata
inventory uses the provider's `note_file_entries` capability when available,
otherwise lightweight per-folder listings, without reading note contents.
LocalCrypt mobile collects ciphertext sizes during batched name discovery, then
converts distinct lengths through the credential-scoped `crypt_sizes` bridge
action in batches of at most 256. It uses rclone's own size conversion without
reading document bytes; invalid or partial results and revoked grants fail the
request. Desktop validates visible names with the same discovery, then obtains
decrypted sizes in one recursive rclone metadata command with hidden entries
excluded. Missing or duplicate note rows fail discovery rather than publishing an
incomplete index. Size requests therefore retain the discovery optimizations.
Filename-only discovery uses the provider's `note_file_paths` capability when available, with
per-folder listings as the fallback. Name-only `list_names` listings avoid rich
metadata, timestamp formatting and sorting when the provider supports them;
ordinary mobile collections use the same lightweight projection. Adapted local
providers retain their existing listing filters. LocalCrypt batches basename decoding across
sibling folders at each depth and decodes repeated basenames once per discovery,
avoiding an rclone process or native bridge request for every folder. It prunes
hidden directories before descent and keeps decoded names only during the call.
Desktop POSIX decode commands use bounded 512-entry / 64 KiB batches to amortize
process startup; Windows retains 128-entry / 24 KiB limits. Mobile bridge batches
remain bounded at 256 entries. These are transient discovery optimizations, with
no persistent filename index or change to authored scripts.
Discovery checks cancellation and containment and stops at 10,000 entries. Serialized
index bytes count toward the existing read budget; note content is not indexed.
Frontmatter is excluded before parsing script fences. Span accounting uses only
CR/LF line boundaries so Unicode separators cannot displace generated output.
The total byte budget is checked before another file is opened. Desktop editing
retires view execution; failed navigation keeps the currently published view alive.
Mobile view runs use the document publication token, independently of unsuccessful
opening attempts, and defer generated-heading jumps until results are published.
`dataview_script.py` is an independent implementation of the documented JSON/view
API subset, including synchronous current-note and quoted-folder page queries.
Inline and nested scripts receive the same read-only `app` compatibility object.
`dv.fileLink` creates runtime-owned link values rendered through the existing
library-path anchor renderer in tables, lists, paragraphs and spans. Ordinary
objects and authored Markdown remain literal output.
It runs authored scripts in a disposable browser worker and returns escaped
Markdown output. `dv.container` exposes a bounded detached element tree for
recursive lists and internal anchors, rather than the browser DOM. Anchor paths
and list text preserve authored output order, with numbered markers for `ol`;
assigning `textContent` replaces an element's children. Anchor paths
are escaped and made relative to the calling note for the existing link resolver.
No Obsidian or Dataview source is bundled. Trust is
enabled by default; worker CSP forbids network access and the host exposes no
write or arbitrary native bridge. Worker messages remain untrusted provider input.

Desktop `ui/dataview.py` adds `NotesMarkdownViewer` only to Notes Library. Its
off-the-record Chromium page executes the shared runtime; `OperationProgress`
owns asynchronous file reads. Each private profile outlives its disposable page
and is retired after the page has completed native teardown. Results render in the existing native Markdown
browser, retaining search, speech and heading controls. Original editor text and
save baselines never receive generated output. Close waits for active reads
before releasing the provider, and stale generations cannot publish results.

Mobile `mobile/dataview.py` uses the attached reading WebView to execute that
same worker. `VaultBrowser` polls bounded read requests, validates the generation
and re-renders results through the existing Markdown preview. Worker permission
is removed from the completed page. Navigation, editing and disposal retire the
run. The worker deadline is 30 seconds; hosts additionally stop waiting after
35 seconds. Data reloads on reopening a note; there is no live file watcher.

`test_text_editor_dataview.py` covers real desktop rendering and the mobile preview
CSP in Chromium, nested view files, JSON, errors, literal output, source preservation,
refresh and provider limits. Mobile `test_notes_library.py` checks result publication
and stale navigation. `document_storage_tools --probe notes-dataview` runs
`dataview_probe.py` on disposable iOS/Android devices to check native worker/JSON
execution, nested views, tables/lists, editing/source preservation, refresh and
visible errors. Raw reports/screenshots stay under ignored test results.

On November 2, 2026, the focused probe passed on a disposable iPhone simulator
and Android phone emulator, including extensionless JSON/view paths, embedded
JSON saving and JavaScript source opening, failed navigation and generated-heading
jumps. The Markdown authoring regressions also passed after the shared draft
refactor. Both QA apps
and disposable devices were removed afterward. This does not certify physical
devices, fold layouts or compatibility with APIs outside the documented subset.

## Notes document ownership

Documents automatically discovers marked libraries in Local and unlocked
LocalCrypt within its bounded two-folder scan. The mobile Notes Library suite
checks Local discovery and opening without a workspace prompt. Its native-bridge
case also discovers and opens a real encrypted library with session-only
credentials, navigates nested notes and history, verifies the credential
association remains nonpersistent, and checks the entry disappears after locking.
This host integration coverage does not certify physical-device presentation.

Direct note links probe their contained provider path without listing sibling
files. Bare wiki names first try the current folder and library root; unresolved
names still require a bounded vault scan and duplicate matches are rejected.
Desktop and mobile LocalCrypt providers share `localcrypt/note_lookup.py`,
which matches the deterministic encrypted basename without decoding unrelated
file names. This lookup applies to attachment links (including `.mp4`) as well
as Markdown links, avoiding a decrypted listing of every folder for bare media
names. Desktop supplies bounded rclone encode/decode commands; mobile
supplies native bridge calls. On POSIX hosts it walks ciphertext through directory descriptors,
avoiding repeated ancestor checks and decoding only candidate full paths. Hidden
candidate paths are excluded after decoding. Deep or oversized raw trees fall back
to the bounded visible-tree scan, which batches directory-name decoding across
each breadth-first level and skips hidden folders. Neither path retains a lookup
index. Root containment, linked/special
file rejection, cancellation, credential checks and the 10,000-entry limit remain
enforced. Ordinary local global lookups reuse an in-memory, 10,000-entry folder-name cache. Validated local
directory inode and nanosecond modification/change times invalidate changed
folders, including changes made outside Logistics. On Windows, a fresh lightweight
name/type fingerprint also detects rapid changes whose directory timestamps are
deferred. Unchanged folders still reuse their richer listings. Providers without a validated
physical directory location keep uncached lookup. No note bodies or persistent
plaintext index are added. Close and credential revocation retire the cache;
late workers cannot repopulate it. Mobile Notes Library navigation history and
scroll positions also remain in memory and clear on disposal; the library's
transient workspace session does not enter persistent Recent history.
The native `notes_audit_probe` checks direct/cold/warm lookups and actual WebView
publication with synthetic ordinary and LocalCrypt libraries; its LocalCrypt
checks also reject plaintext workspace/Recent note names and verify lock cleanup.
For explicit on-device diagnosis, a `notes-open-timing.enabled` marker in the app
cache enables `notes-open-timing.json` with numeric stage durations and cache counts
only. It records no filenames, source text, credentials or error messages. Remove
both files after collecting measurements; disabled libraries emit no timing files.

The desktop Notes library clears `viewer.document_state` when retiring a private
draft, then clears the reading/source/formatted surfaces. Saved byte and rich
baselines therefore retire through the declared shared owner rather than through
separate private viewer attributes. The ownership contract is documented in
[commonUtils Markdown](../../../../Python/commonUtils/docs/development/reference/ui/markdown/markdown.md#internal-ownership-and-embedding-contracts),
and `test_notes_library_desktop.py` verifies that retired drafts retain no saved
byte baseline.

## Notes Library ownership

The mobile library panel owns top-aligned Files, Search and Calendar tabs.
Files and Search reuse one retained scroll/list owner, mounted only in the
selected panel. Files ignores a retained query; Search alone projects results
and owns its query and two scope buttons. Leaving Search cancels its pending
scan; returning restarts the retained query. Calendar remains independently
cancellable. A centered command row below the tabs owns New document, New folder
and Collapse all folders, outside the scrolling area. The Files tab is the root
drop target; the library identity/status footer and redundant library menu are removed.
Desktop uses the same command artwork for its creation and collapse buttons. File row font and touch height are
unchanged.

Compact Files uses `SpeechOverlay(edge_panel=True)` to fill the window's usable
height above document chrome while avoiding hardware/system occlusions. Other
overlays retain their existing bounds. Wide allocations put the document title
inside the article pane via `_document_title_parent`, allowing Files to extend
alongside it; the shared title owner still tracks native mounting and fullscreen.

On mobile, `notes-library:` routes own the full content area, including iPad and
Duo layouts. The outer Workspaces folder column and app destination bar stay
hidden until the library closes. The library floats Files on compact allocations
and pins it beside the article from 840 points of inner width (864 before the
library inset), leaving at least 520 points for the document. Links remains a
floating panel at every width. Document swipes open Files to the right and Links
to the left; the opposite swipe dismisses each floating panel. Selection,
editable controls, horizontal overflow, zoom and multi-touch suppress document
swipes. Android observes drawer touches at the popup before child dispatch;
iOS allows the drawer recognizer to coexist with scrolling. History and editing
actions remain library-owned. Child tools retain that presentation. This is a
presentation policy separate from reader-return trimming, so closing a nested
note editor returns to its library. `notes_fullscreen_probe.py` checks native
geometry through rotation and verifies that closing restores the folder browser.
The focused `document_storage_tools --probe notes-drawers` checks center-document
touch events, native drawer dismissal and compact/pinned layouts through rotation.

`notes.py` provides toolkit-independent marker detection, rooted paths, bounded
reads and immediate-child filtering. Note reads complete short provider reads
through EOF or the 16 MiB ceiling plus one using `runtime.streams.read_up_to`, then
apply the existing size, cancellation and revision checks before decoding.
Desktop `notes_actions.py` contributes the
location command; `ui/notes_library.py` owns its lazy library window and
cooperative workers. Its credential observer uses a Python bound method that
emits the Qt revocation signal, because the session registry holds observers with
`weakref.WeakMethod`; a Qt signal's built-in `emit` method cannot be registered
directly. The workspace action entry carries `storage_scope` while retaining both
local and remote endpoints for transfer contributions. Notes probes only that
local scope only. `NotesLibrary` rejects remote providers through wrapper-aware
`document_remote` before any listing or note reads. Cloud Markdown remains a
standalone read-only document. Local viewers enable editing by default.
`PageStorage` publishes local saves on a worker through `ResourceTextSession`,
checks original bytes and revisions, and retains drafts on failure. Navigation
and closing resolve unsaved changes before retiring the current note.
`test_notes_library_desktop.py` exercises real rclone LocalCrypt and
crypt-remote rejection, nested local note reads and revocation. Mobile's
`test_notes_library.py` covers both encrypted sources with the host native bridge
when `LOGISTICS_MOBILE_BRIDGE` points to its shared library, using only synthetic
credentials and an in-memory remote. Mobile resolves the same location scopes in
`mobile.notes_actions` and presents them through the retained adaptive
reader. `mobile/notes_library.py` owns that presentation through a declared
`NotesHost` contract. The host retains entry-point routing, workspace sessions,
provider resolution and credential lifetimes. The shared native private WebView
supplies memory-only rendering; Notes Library containment and URL policy remain
feature-owned.

`mobile/notes_drawers.py` hosts retained Files and Links panels with the shared
native floating-surface owner. The article stays mounted at full width; overlays
are dismissed on editing, closing and privacy retirement. Document edge swipes
exclude horizontal scrolling, zoom and selection; drawer reverse swipes dismiss.
Native pane buttons use UIKit's horizontal axis preference for header placement.
Floating drawers measure their owner's safe allocation and active UIKit occlusion
regions rather than the window alone, keeping them out of the status/action strip.
File-action dialogs retain their originating drawer across native alert dismissal.
Move/copy forms retain that pane while mounted; Cancel and the mobile route Back
handler restore it without consuming document history. The mutation guard blocks
return while a file operation is running, and disposal clears the retained form.
Forms bind Cancel and Submit to their own retained view. Superseded menus,
callbacks from replaced forms, and actions arriving after a destination change
cannot mutate files or replace a newer presentation. Native dialog results also
check the document epoch before restoring a drawer.
UIKit native pops also restore the originating pane when they expose the same
library beneath a file form. Route trimming clears the form context, including
when navigation skips past the library, so callbacks from removed forms cannot
mutate files. The explicit form-Back path respects the host route guard.
Removing the library route also invalidates decisions from menus that have not
opened a form yet. Delete rechecks the originating document epoch, action request
and destination after unsaved-change and confirmation dialogs, before starting
the filesystem mutation.

`notes_links.py` builds connections on a worker only when Links opens.
The right panel has Outgoing links (selected by default) and Backlinks tabs.
The first stage reads only the current note and resolves its targets; the second
scans library notes for backlinks. Backlink loading and errors stay in their own
tab so outgoing links remain usable while the scan runs. It uses the
same Markdown/wiki-link parser as preview, resolves relative/root/unique suffix
paths, excludes hidden and host-filtered folders, and never saves an index.
Cancellation and generation checks prevent late private results publishing after
closing or changing notes. Scan limits are 5,000 notes, 10,000 entries and 64 MiB;
exceeding them reports an error rather than presenting partial backlinks.
`test_notes_drawers.py` covers connection syntax, navigation, remote wrappers and
late-result retirement; `notes_fullscreen_probe.py` checks native overlay layout
and note history across rotations. Validation covers iPhone, iPad, closed/open/partial
Duo and Android; the Duo and Android gesture probe dispatches document touch events
through the WebView navigation handler. The shared toolbar audit also covers the
failed credential-unlock form. Expanded external-app Live Activities still need
physical-device verification; simulator screenshots do not reproduce that activity.

Mobile libraries publish separate Close and page-history controls to the native
toolbar. The **×** calls `NotesHost.close_session` through the host's session-close
workflow, retiring the library even when page history or compact browsing is
active. The visible **‹ / ›** controls only navigate note history; they stay
disabled at its ends. The documentation reader uses the same controls, with
Close returning through its host route. Android system Back retains its
browse-panel, page-history, then exit ordering.

Remote providers never get a search widget or recursive index. Private note data
stays in memory and credential revocation retires the document. See the
[workspace contracts](../../../development/mobile-workspace-navigation.md#notes-library)
for lifecycle and cross-platform validation.

## Library presentation boundaries

commonUtils owns Documentation Library (`ui.markdown.wiki.WikiPanel` and
`ui.native.markdown.MarkdownWikiView`): heading-based labels and a navigation-only
sidebar. Alt/Option enables document editing without enabling tree mutations.
Logistics owns filename-based notes, provider mutations and Obsidian-folder
choices under `features/notes_library/`. Desktop folder navigation publishes files directly; Notes Library remains an
explicit workspace action. Mobile Workspaces also browses directly without a
mode choice or Notes Library menu entry. The Documents hub owns asynchronous
`mobile/notes_discovery.py` discovery of `.obsidian` directory markers in Local
and unlocked LocalCrypt roots, through two child-folder levels. Scans are
cancellable, generation-checked and bounded by entry/folder limits. They read
names/metadata only, close scan providers, and create a fresh provider when a
library is opened. Locked names are never saved to a discovery index.

Notes creation and moves validate containment and provider capabilities in
`NotesLibrary`. Desktop moves resolve unsaved edits before dispatch; successful
moves refresh loaded folders and remap note history. Mobile moves refresh the
loaded tree, history and reading positions. Existing destinations are preserved;
links are not rewritten. Cloud storage retains its read-only policy.

Focused checks: `test_markdown_library_modes.py` (desktop) and
`test_notes_library_modes.py` (mobile host), alongside the existing Notes Library
and Markdown editor workflow suites. Host checks do not replace native device QA.

Note links resolve on the opening worker through `NotesLibrary.link`: first the
current folder, then the library root, then a unique matching path suffix across
visible subfolders. Extensionless links receive `.md`. Explicit `./` and `../`
links keep relative semantics; hidden configuration and paths outside the library
remain excluded. Lookup is cancellable and limited to 10,000 listed entries,
with no persistent index. Local directory-name listings may be reused in bounded
revision-validated session memory and are cleared on retirement. Ambiguous names require an
explicit path. Desktop and mobile use the same resolver, including LocalCrypt's
decoded provider paths. Mobile's shared renderer also recognizes bare `[[Tech]]`
links in formatted headings. Root-vault offers are covered by actual desktop
local/LocalCrypt browsers and mobile host tests; these are not device QA.

## Notes Library platform parity

Desktop `ui/library_panels.py` supplies recursive library search through
commonUtils' provider search engine, Files/Calendar navigation, connection scans,
and copy/delete context actions through the same `library_files` and
`notes_links` services as mobile. Search/calendar and connection scans have
independently cancellable workers, generation-checked snapshots and paged search
results. Closing waits for all workers before releasing the provider. Folder landing notes and
session reading positions are retained independently of the viewer's history.
Existing Markdown opens in reading mode on both platforms; new Markdown starts
editing. Desktop drag/drop and mobile move forms remain platform-specific controls.

Mobile `library_tools.py` adds heading navigation, properties and raw YAML forms;
`library_document.py` hosts commonUtils' `EditorSearch` over its native Source
input. YAML changes use the shared preservation helpers and reject stale drafts.
Retirement clears retained search inputs and form content. Contents reads actual
rendered heading IDs in preview and parses the current draft for Source jumps.

`test_notes_library_desktop.py` covers recursive modes/order, hidden configuration,
calendar duplicates/confirmation, connection navigation, copy collisions, dirty
delete cancellation, folder landings, positions and worker-close lifetime.
`test_markdown_library_workflow.py` covers literal/Unicode replacement, saving,
heading jumps, YAML/body preservation, stale tools and retirement. The native
Notes Library probe additionally exercises actual text selection, Source search,
YAML application and saved bytes on disposable devices. Evidence belongs under
ignored test results, and host passes alone do not certify native interactions.

The November 2 parity pass passed the native Notes Library probe on an iPhone
simulator and a disposable Android phone emulator, including Source selection
after a non-BMP character, literal replacement, YAML application and save,
formatted keyboard geometry, rotation and drawing navigation. QA apps were removed
after evidence collection. This pass does not certify physical devices or fold
and tablet layouts for the newly added tools.

The follow-up parity review covers delayed desktop Files callbacks after switching
to Calendar, hidden calendar refreshes, saved content/connection refresh, and
discarded notebook resources when opening finishes after close. Failed mutations
resume cancelled background scans so a collision cannot leave a panel loading.
Mobile tool entry requires a completed mode switch; failed input snapshots and superseded Source
requests leave the current draft and mode intact. Property names are fixed while
editing an existing row, and Add Property refuses existing names. Mobile forms wrap
guidance/errors and shorten row captions while retaining full accessible labels.
Focused tests exercise these failure/race paths; the native Notes probe also
exercises property editing, duplicate-name rejection and recovery after a failed
Source switch.

Desktop Save-before-navigation and Save-before-mutation use one deferred action
for Markdown and drawings. Completion resumes it only after a successful save;
failure, close and revocation retire it. A close request during a save takes
priority over navigation without prompting for that save again. Failed drawing
close requests do not survive into later manual saves. Deletion on both platforms
preserves the current history occurrence, including repeated visits to the same
note; retiring the current document disables parent navigation. Mobile folder
creation uses directory metadata from loaded/search rows, so an unopened selected
folder remains the destination without a filesystem probe. Desktop save/close
and platform history/folder regressions cover these workflows.

Mobile Markdown saving flushes native input again after publication. Edits entered
while the write runs remain dirty and prevent navigation; a later flush failure
retains the published baseline for retry. Successful writes, copies and deletes
refresh an active library query and invalidate connections. An already-open Links
panel refreshes asynchronously; dismissing it cancels the queued refresh instead
of reopening the panel. Deletion removes stale search rows before rescanning.
Host workflows cover slow-write input, retry baselines, saved connections and
copy/delete search results. The native Notes probe additionally leaves actual
WebView text ahead of Python during a blocked write and verifies both saved bytes
and the retained newer draft before a second save.
Mobile Markdown naming also retains either supported `.md` or `.markdown`
extension, including mixed case, matching desktop creation.

Formatted editor HTML publishes its bridge identity after script initialization.
Native flush reads a snapshot only when that identity matches the current Python
editor generation. An old page retained during asynchronous replacement therefore
cannot submit patches against the new source blocks. The production-HTML DOM
suite verifies that a mismatched page does not even invoke its snapshot function;
native probes wait for the matching identity before testing queued input.

## Folder browsing cost

Folder expansion reads names and metadata, without opening document bodies.
`NotesLibrary.folders` uses the provider's guarded `list_names` snapshot when
available, avoiding full per-file entries and timestamp formatting. Providers
without that API retain their normal listing; adapted local providers retain
their own namespace and filtering. Document admission and connection reuse still
obtain fresh revisions independently.

Landing-note detection uses `NotesLibrary.folder_pages`; desktop LocalCrypt
encodes candidates in batches of at most 128 rather than spawning a process for
each candidate and alternate directory spelling. Mobile LocalCrypt probes only
the encoded file spelling. Probes retain cancellation and credential checks and
validate physical paths before inspecting them. No additional plaintext index is
persisted. Focused provider tests check real encrypted landing-note detection and
that a folder page batch never reads document content.

Mobile row construction uses the host's existing surface-paint batch for each
row, so provisional button, icon and selection styles paint only their final
state. Rendering yields after eight steps or eight milliseconds of work, retaining
cancellation without a timer round trip for every cached row. Controls are built
offscreen and published in one batch; row reuse, holds and drag bindings retain
their existing retirement rules. Desktop uses its existing Qt tree and shares
the names-only provider improvement.

The optional `notes-folders` native probe separates listing, landing-note probes,
row work and publication for local and LocalCrypt folders on Android/iOS. Its
fixture includes 40 notes and four landing-note folders and checks cold and
retained-directory expansion. Host regressions cover final-paint counts, bounded
timer overhead, cancellation and provider fallbacks. Timings from an emulator or
simulator do not establish performance on a physical Samsung S8+.

The combined `folder-feedback` native probe first exercises the Android item
menu for root and nested LocalCrypt moves, verifies decrypted destination bytes
and ciphertext retention, then runs both storage types through cold and repeated
folder expansion. Each expansion must publish all 45 rows together and must not
open document bodies. Startup bounds, active phases and task stacks are retained
in ignored test evidence. Its acceptance deadline is bounded at ten minutes;
manager-owned disposable devices and QA packages are removed by the runner.
Fixture creation runs in one worker before measurement. Acceptance uses the
lightweight phase counters; detailed Python call profiling is opt-in through the
probe class because it also instruments native bridge and event-loop calls.

## Scoped desktop library tabs

`ui/library_workspace.py` hosts independent document-only Notes Library owners
inside `ScopedTabBar` groups, using the IDE's bounded horizontal drag geometry.
The outer owner retains folder/search/calendar navigation; inner owners retain
editors, resource sessions and workers. Provider leases are shared without
revoking sibling tabs. Group focus controls active file references and Save;
shortcuts stay within each child widget. Mutation preparation resolves drafts,
and successful moves/deletes remap or retire affected tabs. Moves retain tab
identity, repeated history occurrences, cursor and reading positions; deletion
removes earlier visits from every tab's history. Deleting an inactive dirty tab
still resolves its draft. Mutations do not run during pending document reads. Close waits for
cooperative worker retirement. Focused tab tests cover independent drafts,
side-by-side groups, native Save-key dispatch, rename placement and LocalCrypt
lease release. Existing desktop library tests cover favourite reopening through
the tabbed host.

The tab host also routes New to the shared library navigator and scopes inner
shortcuts to their document subtree; Save has one active child handler. Focus
changes inside side-by-side editors update the active document reference. Desktop Files/Calendar
stays visible, with a non-collapsible splitter pane. Document navigation sits in
the Markdown toolbar (or the document control row for source files/drawings),
using commonUtils' shared `MarkdownNavigation` group beside Contents and the
other document tools. Each tab's buttons use its own document history. Switching tabs does not
append history; parent-folder navigation uses the clicked tab's current file. Child operation
footers are hosted below the outer splitter, selected with the active tab
(including its first pending open), and retired when the child closes. Data-view
reads, Markdown rendering, source-file saves, embedded notebook saves/exports and
PDF page reads share that footer placement. Notebook canvas replacement retires
its previous progress widget before creating the next one. Tabs
keep Markdown notices, rendering indicators and source-save results in one horizontal
footer row, alongside active operations; long notices are elided with full tooltips
and accessibility descriptions. Empty
messages collapse and switching documents clears stale source-save messages. Tabs
without a completed open and the empty library clear the outer document/history
projection; Save does nothing until a document is available. Tab regression tests cover history dispatch,
footer placement, cancellation and cleanup.

## Library file dragging

Desktop Files includes a non-draggable Library root row as an explicit drop
destination. Mobile `library_drag.py` uses Android local drag listeners and UIKit
local drag/drop interactions; native payloads contain an opaque per-library token,
not a document path or bytes. Icon holds start drags; filename holds and row
ellipsis buttons open the same mutation menu. Folder names remain drop targets.
Floating drawers retire before presenting the native menu so they cannot cover
it; cancelling restores the originating drawer. Bindings retire with recycled
rows and the library owner.
`move_entry_to` shares move-form and drag publication, resolves edits, blocks
competing note navigation during a move, remaps histories/positions and refreshes
loaded folders while retaining the browsing drawer. Root moves, self/descendant
drops and collisions preserve source files. Host checks cover file/folder/root
moves, current-note remapping and existing calendar/create flows. These checks do
not certify native finger-drag appearance or physical-device gesture delivery.


## Feature extraction validation

The extraction passed desktop main-window destination/lifecycle tests, library
editing/provider regressions, scoped tab and folder-mode tests, preference and
registry tests, shared host/picker/resource tests and mobile library/authoring
host suites. Payload startup, import manifests, lint and documentation layout
were checked. Native Qt captures cover the empty destination, two libraries and a
detached session. These checks exercise feature independence, old favourites,
root deduplication, cancelled close and retained drafts on feature disable.

The focused Notes Library probe passed on a disposable iPhone simulator and
Android phone emulator, including formatted/source editing, notebook saves,
search cancellation and native save-time input. The standalone Documents probe
passed on both platforms, including text workspaces and Markdown previews.
Each runner removed its QA application and disposable device. This scope does
not certify physical devices or every tablet/fold layout.

The architecture scan also identified existing feature-to-host imports outside
Notes Library. The extraction's new model, service publication boundary and
reviewed desktop adapters are covered separately; those unrelated imports are
not evidence of a passing whole-repository architecture scan.

## Percent-encoded local links

Markdown source admission is bounded at 16 MiB. Mobile Notes Library supplies an
explicit shared-renderer profile with the same 16 MiB source bound, a 96 MiB
HTML output bound and a 66 MiB encoded-image output budget. Other native preview
consumers retain the shared renderer's smaller defaults. Notes Library media
allows 48 MiB of raster bytes per render, retaining the 8 MiB/16-megapixel bound
per image. Native image tags request lazy loading and asynchronous decoding.
Private rendered pages have a separate 128 MiB in-memory HTML bound, allowing
room for host links, styling and scripts. These are allocation guardrails, not
measurements of maximum safe page sizes on each device. The Android
appearance adapter respects each private surface's configured HTML bound.
Opening failures dismiss the loading panel, retain the published document,
and show a native error dialog instead of placing the error above the page.
The HTML bound is checked after link rewriting and data-view decoration. Native
HTML admission precedes history changes and editor retirement, so a synchronous
WebView rejection preserves the current document and draft. Embedded file opens
and PDF page-turn failures use the same host-owned dialog. Host regressions cover
an image-heavy page above 32 MiB, Markdown source above 2 MiB, decoration growth, native rejection from both
reading and editing, and retained page-turn state. Formatted-editor failures also
show a dialog while retaining the Source fallback and its unchanged text. These
host checks are not device proof.

Note navigation, outgoing links and backlinks try one URL decode first, then the
literal path spelling only when the decoded lookup has no matches. A decoded
ambiguity remains unresolved rather than falling through to a literal filename.
Each spelling retains relative/root lookup rules and the library's containment
and access checks. Images and videos use the same resolver and decoded-first ordering as navigation.
Missing or ambiguous images display a reason in native previews and a readable
in-memory placeholder in the desktop viewer. Access, invalid image and size/budget
failures also produce reasons; the authored Markdown remains unchanged. Fragments stay separate from filename lookup.

Connection scans normalize direct relative/root candidates and apply the same
library containment checks as navigation before considering a literal fallback.
Desktop absolute file links preserve their query/fragment and must have the same
file-URL host as the current document.

## Navigation and mutation projection

`navigation.py` owns pure `PathChange` history/position transformations. Visits
remain ordered occurrences, including repeated visits to the same path; deletion
retains the cursor relative to surviving visits. Desktop windows, scoped tabs and
mobile mutations share these rules. `MutationResult` distinguishes committed
filesystem destinations from folder refresh and saved-reference failures, so
refresh cancellation cannot undo an authoritative move result. Focused desktop
and mobile Notes Library suites exercise these transitions.

## Desktop document panes

`ui/document.py` owns `NotesDocumentPane` and shared document presentation. Scoped
tabs instantiate QWidget document panes, without a second Files tree, Calendar,
search worker or library menu. The outer workspace retains those controls. Each
pane retains its own history, provider lease, Markdown/source/notebook/preview
resources, connections and operation footer; the workspace selects the active
projection. `ui/library_connections.py` owns the document Links panel independently
of library navigation. Desktop library and scoped-tab regressions cover the split,
including private leases, shortcuts, footer selection and worker retirement.
Document panes retain the outer library label for root breadcrumbs; scoped-tab
tests assert that label as well as document identity.

## Test scope and DataView execution

`Python/tests/editing/test_notes_library_desktop.py` retains daily mounting,
navigation, source-preservation and video-routing checks without starting real
playback. `test_notes_library_integration.py` keeps real Qt/VLC decoder and
encrypted-provider journeys at `EXTENDED`; full runs still include them.
Mobile editing tests retain their independent native-adapter and session coverage.

Desktop DataView uses a disposable, off-the-record Chromium page. The viewless
computation page is marked visible while it performs document work, avoiding
background worker-message throttling between provider reads. It is hidden and
destroyed on completion or cancellation; no browser widget is displayed. Qt
documents this visibility state separately from a connected view's visibility in
the [QWebEnginePage API](https://doc.qt.io/qt-6/qwebenginepage.html#visible-prop).
DataView regressions exercise actual scripts/provider reads and profile retirement;
the shared Qt fixture also fails unhandled callback exceptions.

## Document preparation and publication

`preparation.py` returns named `PreparedDocument` results before desktop UI
publication. An abandoned result has one idempotent close path for source leases,
notebooks, media resources and file previews. Publication retains each format's
existing editor behavior. Mobile `mobile/library_opening.py` owns document
admission, preparation, publication tokens, history and native page callbacks;
the browser retains library navigation. `mobile/preparation.py` shields prepared
reads and disposes late results when their awaiting task is cancelled. A source
resource is never closed while its preparation worker still uses it. Desktop
late-open regressions and mobile cancellation/resource checks cover this boundary.

## Shared link policy

`link_policy.py` owns decoded/literal spelling precedence, exact extensionless
files, relative/root candidates and suffix ambiguity. Navigation supplies bounded
live provider probes; connection scans supply their detached path/suffix inventory.
Neither changes the other's I/O strategy. Desktop/mobile link, containment, media
and encrypted file-operation regressions cover this boundary. Dataview keeps its
separate explicit path contract.

## Connection scan reuse

`connection_index.py` retains parsed link targets and word/character counts, never
note bodies, in at most 8 MiB of accounted session data and 5,000 entries. Desktop
document panes share their library's index; each pane keeps independent media and
editor state. Scans still validate the visible inventory and each note's provider
revision, so external edits are observed without a file watcher. Providers without
revisions read afresh. Serialized body admission coalesces simultaneous reads of
unchanged notes; cancellation remains cooperative and retirement does not wait
for the admission lock. Writes/mutations invalidate retained entries. Closing a
child leaves siblings' index intact; library retirement clears it and prevents
late workers from repopulating it. Original scan count and byte limits still apply
to reused data. Focused connection tests verify reuse, external edits, concurrent
reads and library lifetime, alongside desktop/mobile workflow regressions.

Dataview retains upfront index preparation for its synchronous `dv.pages()` and
`app.vault.getMarkdownFiles()` compatibility API. Deferring that request by
re-executing authored scripts would change execution semantics; no script replay
is introduced by the connection optimization.

## Structured file preview content

`FilePreview.content()` returns `PreviewContent` with image bytes, MIME type,
metadata and an admitted video URL. Desktop consumes image bytes directly through
the existing oriented image decoder; it does not serialize or regex-parse HTML.
Mobile and existing HTML callers use `FilePreview.page()`/`PreviewContent.html()`.
PDF workers return structured page content on desktop and retain the same deferred
resource retirement. Library/tab and mobile preview regressions cover image/PDF/
video/unknown files, cancellation and cleanup; a native desktop image contract
check refuses any HTML serialization while opening the preview.

## Native links, local images and speech acceptance

`mobile_build.validation.document_storage_tools --probe links-images-voices` runs
inside a disposable Android emulator or iOS simulator. The fixture holds the
backlink scan while checking that outgoing links remain usable, selects both tabs
through native controls, follows a backlink and rotates the workspace. It also
checks local image list/tile thumbnails and the information panel, corrupt-image
fallback and exclusion of network/cloud content. Read-aloud checks open and reopen
Settings without a manual load action, restore a missing saved voice to System
default, and exercise default playback when the native engine is available.
The report distinguishes native engine availability from the controlled missing-voice
fallback assertion. This does not replace physical audio or accessibility testing.
The runner records source fingerprints and evidence before removing its owned
devices; do not select a physical `--device` for this acceptance pass.

## Native copy and panel interaction acceptance

The managed `document_storage_tools ios|android --probe notes-drawers` probe
checks swipes from the New/Open cards and verifies that a native Open-card tap
still works. It dispatches through the native view hierarchy, exercises the outer
edges of the 48-point Notes Library and file-browser menu controls, and checks
that adjacent filenames do not open. File and folder copies use synthetic local
and LocalCrypt storage, preserve contents and default to sibling ` - Copy` names;
repeated library copies verify numbered conflicts. Workspaces Copy is selected
through the native menu. Cloud/server copy behavior is outside this probe.

The probe also checks portrait/landscape transitions. iOS coordinate input covers
open-document swipes, file/folder holds and note actions. Breadcrumb hit testing
uses the visible intersection with its horizontal scroll viewport; the secondary
toolbar must remain attached and visible. Discovery and startup readiness are
awaited before interactions. Evidence is saved before owned QA apps and temporary
devices are removed; this acceptance pass does not target personal devices.
