# Notes Library development

Notes Library browses, edits and organizes Markdown, source files and drawings
in local and unlocked LocalCrypt folders. Desktop has a dedicated destination.
On Android and iOS, open a library from Documents. See the
[Notes Library guides](../notes_library.md) for user workflows.

## Try a search ranking change

On desktop, create a temporary folder with `needle2.md`, `needle10.md` and
`Body.md`. Put the word `needle` inside `Body.md`. Choose **Notes Library →
Open Library** and select the folder. In **Search**, choose
**Search within Documents** and search for `needle`. The filename hits appear
in numeric order before the body-only hit. In **Search in File Names**, only
the two filenames match.

As a disposable experiment, reverse which group comes first by negating the
`content_match` sort key in
`Python/features/notes_library/library_files.py:ranked_search_rows`. Keep the
natural filename and path tie-breakers. Both desktop and mobile call this
function when publishing results. Adjust the ordered expectation in
`test_rooted_search_ranks_names_before_bodies_and_name_scope_never_reads_text`
so `Body.md` comes first, leaving the filename-only assertions intact. Relaunch
desktop, repeat the query and check both scopes.

From the checkout root with the [desktop environment](../../../development/setup/getting-started.md) set up, run:

```sh
python3 dev.py test desktop --exact-file Python/tests/editing/test_notes_library_folders.py
```

Expect the synthetic folder suite to pass, including the new order, filename
search without body reads, hidden-path filtering, cancellation and the first
page of saved matches.

## Destination and feature contract

Desktop `Python/features/notes_library/__init__.py:register` contributes
`notes_library.workspace` and browser folder actions from `notes_actions.py`.
Home receives the page through the launch catalog. `ui/page.py:NotesLibraryPage`
uses the Documents workspace lifecycle with its own document destination and
docking group. An explicit **Open Library** accepts an unmarked folder.
**Open as Notes Library** is offered for folders with a `.noteslibrary` file
or `.obsidian` directory. Reopening the same identity focuses the retained or
detached session. Ordinary local identity uses the normalized physical root;
private identity includes the provider, credential context and contained root.

Desktop feature disable prevents new opens and retains the destination while
sessions need saving or closing. Notes Library's preference was seeded once
from Text Editor and is now independent. Markdown and source files use shared
document authoring. Drawing opens and creation require Notebooks enabled.
`Python/tests/application/test_notes_library_hosting.py` covers rail, workspace,
deduplication and disable behavior.

## Notes Library ownership

The feature owns library identity, navigation and mutations. Its provider
supplies listing, access and writes. The host supplies the destination,
picker and native presentation through adapters.

### Notes document ownership

`notes.py` owns the rooted model and filename routing. Supported entries include
Markdown, recognized source text and enabled notebooks. `DocumentResource`
owns the source baseline and verified provider writes. Source-file saves
preserve BOM, encoding and line endings. Opening JSON or JavaScript as source
displays text. For standalone editors and shared authoring, see
[Text Editor development](../../text_editor/development/development.md).

In-library previews handle images and PDFs through the shared document preview
service. Other unsupported formats display metadata. Selecting a video hands
off to Video Player while retaining the current library document. Markdown media
resolves on demand through the library, with an active access grant, and retires
with the page. Mobile inline Play also goes through audio consent. Test routing
and cleanup in `test_notes_library_tabs.py` and the mobile Notes Library suite.
For shared PDF rendering, see [continuous pages](../../pdf/development/development.md#continuous-pages).

## Shared link policy

`notes_links.py` resolves the current folder, then the library root, then a
unique suffix across the contained library. Extensionless links try exact
current-folder and root filenames before trying `.md`. Resolve the URL-decoded
spelling first, then the literal spelling if decoded lookup had no matches.
A decoded ambiguity remains unresolved. Fragments stay separate from filename
lookup. Reject hidden, out-of-root, linked or otherwise inadmissible targets.
Images and videos use the same precedence. A bounded suffix inventory can
serve multiple image lookups in a single render.

Connections use this same policy. Scans consider supported file paths but read
only Markdown bodies. `ui/library_connections.py` owns the Links panel within
each document pane. It refreshes after saves, mutations and tab activation.
`test_notes_library_connections.py` covers resolution and scans. Use
`test_notes_library_desktop.py` and the mobile `test_notes_library.py` for
rendered error placeholders, including failed media resolution.

`connection_index.py` keeps parsed targets and word/character counts within
8 MiB and 5,000 entries per library session. It revalidates note revisions
before reuse and reads afresh when a provider lacks revision support.
Mutations invalidate entries. Retiring a library clears the index and rejects
late writes. The connection suite exercises reuse, external edits and lifetime.

## Library presentation boundaries

### Notes Library platform parity

On both hosts, Files owns folder browsing and file commands. Search retains
independent Filename and Document content inputs, results and pagination.
Scope changes cancel pending work and invalidate publication before restoring the
target scope. Mutations and saves invalidate finished queries. Calendar scans
names only. Breadcrumbs probe for a folder's landing note through the same
provider as Files. Showing a landing note follows ordinary save and history
rules. If that note is already open or absent, the crumb reveals the folder.

### Folder browsing cost

`library_files.search` shares rooted scanning and cancellation across hosts.
Ordinary filename search can provisionally publish saved matches after
provider revalidation. The provisional pass stops at the first useful page
(50 matches), then live traversal reconciles the complete result. Filename
search reads names only. Content search reads visible Markdown as needed.
Partial listing errors can retain valid matches. Hidden folders and mobile
folder visibility apply before descent and before publication of saved rows.
See [directory index admission](../../../development/architecture/file-browser.md#directory-index-admission-and-foreground-demand)
for shared coordinator ownership.

LocalCrypt listing reuses `indexed_list`, with ciphertext fingerprint validation
and bounded provider memory or credential-sealed records. It keeps decoded names
out of the ordinary SQLite index. Credential change or final mobile lease release
retires access and plaintext listing state. Direct links still probe live provider
metadata. Bare name lookup can use deterministic encrypted basenames through
`Python/features/rclone/localcrypt/note_lookup.py`, with a bounded visible-tree
fallback. Desktop and mobile inject their own rclone/bridge calls.

### Scoped desktop library tabs

`ui/notes_library.py` owns the workspace. `ui/document.py:NotesDocumentPane`
owns each tab's provider lease, history, embedded editor or reader, Links panel
and status. The workspace retains Files, Search and Calendar once across tabs
and split groups. Normal navigation replaces the active document through
Save/Discard/Cancel. Explicit `new_tab=True` opens or focuses a separate pane.
`test_notes_library_tabs.py` checks pane-local state, worker retirement and
cancelled navigation.

### Library file dragging

Desktop Files drag/drop uses the same library move workflow as the selection
menu. A folder target receives the dragged entry. Empty sidebar space targets
the root. Move rejects the source or its descendants as destinations and
requires a contained, unoccupied target. Read-only sources cannot start a
mutation. Test the move and its presentation in `test_notes_library_desktop.py`.

## Mobile browsing and document lifecycle

Documents discovers marked local and unlocked LocalCrypt libraries via
`Python/mobile/notes_discovery.py`. Discovery is bounded and stops descending
at a library root. `Python/mobile/obsidian.py` is the compatibility host for
the feature's `VaultBrowser`. `Python/mobile/composition/presentation.py:notes_host`
injects app callbacks, including the rooted Move picker and playlist speech.
Standalone cloud Markdown uses the remote reader. A Notes Library session
requires local or unlocked LocalCrypt storage.

| Change | Owner under `Python/features/notes_library/` |
| --- | --- |
| Files, history, opening and return context | `mobile/notes_library.py:VaultBrowser` |
| Retained search inputs, result rows and scroll | `mobile/library_panels.py:LibraryPanels` |
| Active document, admission, leave decisions, search, media and retirement | `mobile/library_opening.py:LibraryDocuments` |
| Source and Markdown drafts | `mobile/library_text.py` and `mobile/library_document.py` |
| Deferred reads and cleanup | `mobile/preparation.py` |

The host dispatches Back and Close through
`Python/mobile/session_workflows/transitions.py`. Back first dismisses floating
controls or browsing panels and cancels any pending document load. A successful
open from Search records the scope, query, selected result and scroll. Returning
flushes the active editor and resolves Save/Discard/Cancel before clearing it.
Cancel and failed saves leave the draft active. When scope and query still match,
the panel restores row and viewport after returning. Privacy transitions
invalidate Search and Calendar callbacks before hiding content. A retained query
can resume in the visible panel after unlock.

The previous document remains published until its replacement is ready. Publish
only if provider access, navigation generation and native HTML admission still
agree. Rejected loads leave history and drafts intact. Dispose late results and
keep a provider lease until the worker has stopped using it. Desktop
`preparation.py:PreparedDocument` likewise owns cleanup for abandoned results.
Mobile source admission is 16 MiB, rendered HTML 96 MiB and encoded images
66 MiB. Raster media has a separate 48 MiB aggregate and 8 MiB/16-megapixel
per-image cap. Private WebViews bound in-memory HTML at 128 MiB. These guard
allocation, and native capacity varies by device.

### Rename, Move and Markdown preparation

Rename stays within the current parent. Renaming a folder can also rename its
matching landing note. Move retains the basename and uses a rooted picker
that borrows the provider without taking over its lease. Keep the original
location and draft if a required save fails. `navigation.py:PathChange`
updates history and reading positions, preserving repeated visits. A committed
filesystem move remains authoritative even if the list refresh or saved
reference update fails. While mobile prepares Formatted mode, Cancel restores
the reader and invalidates late publication.

### Search round-trip checks

Run these from the checkout root with the mobile host test environment:

```sh
python3 dev.py test mobile --exact-file mobile_build/tests/editing/test_notes_library_panels.py
python3 dev.py test mobile --exact-file mobile_build/tests/documents/test_notes_library.py
```

Host checks cover restored queries, panel lifetime, discovery, document
publication, and private access. Use the managed `document_storage_tools`
runner and its Notes Library and `notes-markdown-feedback` probes for native
rows, save and return flows. See [mobile commands](../../../development/build-release/mobile-launchers.md)
for runner setup and [local validation artifacts](../../../development/testing/validation-artifacts.md)
for evidence storage. Physical gestures, keyboard geometry and fold/rotation
behavior are separate acceptance checks.

## Notes Library data views

`dataview.py` finds complete top-level `dataviewjs` fences outside frontmatter.
It records source ranges and brokers bounded, read-only `ViewFiles` requests
through `DocumentResource`. The render allows 64 blocks, 1 MiB of script
source and 128 read requests. Individual file reads cap at 2 MiB and
aggregate reads at 8 MiB. Discovery caps the inventory at 10,000 entries and
charges serialized metadata against that budget. Where supported,
`note_file_entries` reports Markdown paths and sizes for
`app.vault.getMarkdownFiles()` without reading note bodies. LocalCrypt gets
plaintext sizes from credential-scoped ciphertext size conversion. Invalid
metadata or revoked access fails the request.

`dataview_script.py` implements an independent subset of the Obsidian Dataview
and vault APIs. See the [supported script surface](../user/user.md#json-data-views-in-notes-library).
Each render uses a disposable worker with no host write API or network access.
Trust is enabled by default. Generated output is escaped Markdown, with
runtime-owned links through the library resolver and a bounded detached tree
for `dv.container`. The worker deadline is 30 seconds and hosts stop waiting
after 35 seconds. Navigation, editing and disposal retire runs. Reopening
refreshes data. Generated results never enter editable source or save baselines.

Desktop `ui/dataview.py` uses an off-the-record computation page kept visible
to avoid worker-message throttling. Retire the page before its profile. Mobile
`mobile/dataview.py` uses the attached reading WebView and removes worker
permission after publication. `test_text_editor_dataview.py` runs real Chromium
fixture scripts and checks source preservation and bounded requests. The
managed `notes-dataview` probe exercises native execution. Those checks cover
the implemented subset with synthetic inputs.

## Playlist playback and storage

`playlists.py` scopes playlists to provider reader-state identity and library
root. Entries hold stable IDs and provider-relative Markdown paths.
Transactions update only an existing matching playlist and entry. A newer
position supersedes pending checkpoints. Reordering preserves the active ID and
position. Removing or repairing the active entry stops it and clears position.
When its content changes, Play starts that entry from the beginning. Repair or
remove a missing reference from the playlist detail.

Protected buckets use the catalogue's credential-bound ZIP cipher. Providers
without a persistent reader-state key use session memory. Unreadable encrypted
buckets stay available for recovery or explicit clearing. `playlist_queue`
uses the speech engine's word timing for signed skips. The current note can use
already-rendered text, including visible generated results. Upcoming entries
are prepared from admitted Markdown without running scripts or reading embed
targets. Reads cancel when access changes.

On mobile, `notes_host` supplies callbacks to `PlaylistSpeech`. With lock-screen
continuation enabled, at most one bounded adjacent passage on either side stays
in memory. Locked playback cannot fetch more text and shows a generic title
for protected content. Unlock and press Play when the prepared text runs out.
`mobile_build/tests/editing/test_playlist_speech.py` checks media routing and
zero provider reads during locked seeking. System controls, audio routing and
call interruptions require native acceptance.
