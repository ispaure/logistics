# Notes Library development

[Notes Library guides](../notes_library.md) · [Implementation brief](../../../development/notes-library-feature-brief.md)

| Change | Owner and focused tests |
| --- | --- |
| Model, containment, links and mutations | `Python/features/notes_library/notes.py`, `notes_links.py`, `library_files.py`; desktop/mobile Notes Library suites |
| Desktop session destination | `ui/page.py`, `desktop/documents.py`, `desktop/sidebar.py`; `test_main_window.py` |
| Desktop documents and groups | `ui/notes_library.py`, `ui/library_workspace.py`; `test_notes_library_desktop.py`, `test_notes_library_tabs.py` |
| Mobile library | `mobile/notes_library.py`, library panels/tools/editors; mobile Notes Library and Markdown library workflow suites |
| Shared mobile authoring | `services/documents/authoring/`; mobile Markdown editor, provider and workflow suites |
| Feature state and payload | Desktop runtime preferences, mobile preferences/features, owning source manifests; feature-preference/mobile-feature and packaging tests |

## Destination and feature contract

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
Desktop places a shrinking rich-text path beside history; mobile uses a compact
row below the document controls. Only folders with a same-named `.md` are links
and underlined, both in the path and in Files. The shared fitting policy reserves
space for the current filename before shortening ancestors. Closing or locking
the library clears the displayed path.

Focused validation covers folder-note underlines, inactive ancestors, filename
priority, file-type transitions and history in desktop/mobile host suites. Native
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
checks, cancellation and byte/request budgets. It does not recursively index files.
Frontmatter is excluded before parsing script fences. Span accounting uses only
CR/LF line boundaries so Unicode separators cannot displace generated output.
The total byte budget is checked before another file is opened. Desktop editing
retires view execution; failed navigation keeps the currently published view alive.
Mobile view runs use the document publication token, independently of unsuccessful
opening attempts, and defer generated-heading jumps until results are published.
`dataview_script.py` is an independent implementation of the documented JSON/view
API subset: it runs authored scripts in a disposable browser worker and returns
escaped Markdown output. No Obsidian or Dataview source is bundled. Trust is
enabled by default; worker CSP forbids network access and the host exposes no
write or arbitrary native bridge. Worker messages remain untrusted provider input.

Desktop `ui/dataview.py` adds `NotesMarkdownViewer` only to Notes Library. Its
off-the-record Chromium page executes the shared runtime; `OperationProgress`
owns asynchronous file reads. Results render in the existing native Markdown
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

Direct note links probe their contained provider path without listing sibling
files. Bare wiki names first try the current folder and library root; unresolved
names still require a bounded vault scan and duplicate matches are rejected.
LocalCrypt matches the deterministic encrypted basename without decoding unrelated
file names. On POSIX hosts it walks ciphertext through directory descriptors,
avoiding repeated ancestor checks and decoding only candidate full paths. Hidden
candidate paths are excluded after decoding. Deep or oversized raw trees fall back
to the bounded visible-tree scan, which batches directory-name decoding across
each breadth-first level and skips hidden folders. Neither path retains a lookup
index. Root containment, linked/special
file rejection, cancellation, credential checks and the 10,000-entry limit remain
enforced. Ordinary local global lookups reuse an in-memory, 10,000-entry folder-name cache. Validated local
directory inode and nanosecond modification/change times invalidate changed
folders, including changes made outside Logistics. Providers without a validated
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
through EOF or the 2 MiB ceiling plus one using `runtime.streams.read_up_to`, then
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

`notes_links.py` builds connections on a worker only when Links opens. It uses the
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
with no persistent index or decoded-name cache. Ambiguous names require an
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
Landing-note detection uses `NotesLibrary.folder_pages`; desktop LocalCrypt
encodes candidates in batches of at most 128 rather than spawning a process for
each candidate and alternate directory spelling. Mobile LocalCrypt probes only
the encoded file spelling. Probes retain cancellation and credential checks and
validate physical paths before inspecting them. No additional plaintext index is
persisted. Focused provider tests check real encrypted landing-note detection and
that a folder page batch never reads document content.

## Scoped desktop library tabs

`ui/library_workspace.py` hosts independent document-only Notes Library owners
inside `ScopedTabBar` groups, using the IDE's bounded horizontal drag geometry.
The outer owner retains folder/search/calendar navigation; inner owners retain
editors, resource sessions and workers. Provider leases are shared without
revoking sibling tabs. Group focus controls active file references and Save;
shortcuts stay within each child widget. Mutation preparation resolves drafts,
and successful moves/deletes remap or retire affected tabs. Close waits for
cooperative worker retirement. Focused tab tests cover independent drafts,
side-by-side groups, native Save-key dispatch, rename placement and LocalCrypt
lease release. Existing desktop library tests cover favourite reopening through
the tabbed host.

The tab host also routes New to the shared library navigator and scopes inner
shortcuts to their document subtree; Save has one active child handler. Focus
changes inside side-by-side editors update the active document reference.

## Library file dragging

Desktop Files includes a non-draggable Library root row as an explicit drop
destination. Mobile `library_drag.py` uses Android local drag listeners and UIKit
local drag/drop interactions; native payloads contain an opaque per-library token,
not a document path or bytes. Filename holds start drags; row ellipsis buttons
retain mutation menus. Bindings retire with recycled rows and the library owner.
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
