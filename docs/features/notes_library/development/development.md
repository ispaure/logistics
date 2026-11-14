# Notes Library development

Desktop has a Notes Library destination. Android and iOS discover marked local and unlocked LocalCrypt libraries in Documents. See the [user guides](../notes_library.md).

## Try a search ranking change

On desktop, open a temporary folder as a library with `needle2.md`, `needle10.md` and `Body.md` containing “needle”. Document search ranks the two filenames numerically before the body hit. Filename search returns only those filenames. Negate the `content_match` sort key in `Python/features/notes_library/library_files.py:ranked_search_rows`; preserve filename/path tie-breakers. Update the order in `test_rooted_search_ranks_names_before_bodies_and_name_scope_never_reads_text`.

From the checkout root, expect the body hit first in document search and zero body reads in filename search.

```sh
python3 dev.py test desktop --exact-file Python/tests/editing/test_notes_library_folders.py
```

## Notes document ownership

`register`, `notes_actions.py` and `ui/page.py` own desktop entry points. Explicit Open Library accepts unmarked folders; browser discovery requires `.noteslibrary` or `.obsidian`. Reopen focuses the same normalized root/provider identity. Disable blocks new opens while pending sessions can save or close.

`notes.py` routes Markdown, source and enabled notebooks. `DocumentResource` owns revision-checked writes and preserves encoding, BOM and line endings. The preview service handles images and PDFs; video hands off while retaining the current document. See [shared authoring and source editing](../../text_editor/development/development.md).

## Navigation, search and links

- `ui/notes_library.py` shares Files, Search and Calendar across tabs. `ui/document.py:NotesDocumentPane` owns each tab's editor, history, Links and lease. Normal navigation resolves Save/Discard/Cancel. Explicit new-tab navigation opens or focuses a separate pane.
- `library_files.search` cancels work on scope switches, restores each scope's query and invalidates results on mutation. Filename search reads names only and can provisionally show 50 revalidated saved hits. Content search reads visible Markdown. LocalCrypt validates ciphertext revisions and keeps decoded names out of the ordinary index.
- `notes_links.py` tries current folder, root, then unique contained suffix. Extensionless lookup tries exact names before adding `.md`. Try decoded spelling first and literal only on no match. Reject ambiguity, hidden entries and links outside admitted storage. `connection_index.py` caches parsed Markdown by revision, invalidates on mutation and retires with the session.
- Rename stays in the parent and can rename a matching landing note. Move retains basename and requires an unoccupied contained destination outside the moved subtree. `navigation.py:PathChange` updates history after commit. Keep the draft and path if a required save fails. A failed refresh leaves the committed move authoritative.

## Mobile browsing and document lifecycle

`Python/mobile/notes_discovery.py` stops at a marked root. Compatibility host `Python/mobile/obsidian.py` receives callbacks from `composition/presentation.py:notes_host`. Within the feature, `mobile/notes_library.py:VaultBrowser` owns Files/history, `library_panels.py` owns retained queries and scroll, and `library_opening.py:LibraryDocuments` admits and retires documents. `preparation.py` owns deferred reads and cleanup.

Back dismisses transient controls and cancels pending loads first. Before returning from an open Search result, flush the editor and resolve Save/Discard/Cancel. Restore row and viewport for the same scope/query. Cancel or failed save retains the draft. Publish a replacement only after access, navigation generation and WebView admission checks. Hold the lease until abandoned workers retire. Lock invalidates callbacks before hiding content.

```sh
python3 dev.py test mobile --exact-file mobile_build/tests/editing/test_notes_library_panels.py
python3 dev.py test mobile --exact-file mobile_build/tests/documents/test_notes_library.py
```

Expect restored panels, guarded publication and retired private access. For native rows, keyboard and return flows, use the Notes Library and `notes-markdown-feedback` probes. [Mobile commands](../../../development/build-release/mobile-launchers.md)

### Files and Links drawers

From **Browse Notes Library** or **Links**, follow `VaultBrowser` to
`mobile/drawers.py:NotesDrawers`. Files stays beside the document on wide or
vertically folded layouts. Compact Files and Links use overlays. The feature
owns those transitions, the pending File actions choice and Back. It cancels
choices and retires overlays when the library closes.

`drawer_gestures.py` binds UIKit recognizers and Android touch listeners.
It defers to breadcrumbs, web content and embedded editors where those surfaces
own the gesture. `notes_swipe.py` handles the Markdown document's own swipe
admission. `drawer_motion.py` owns drawer animation and respects reduced motion
and the Android E Ink setting. Disposal detaches opening observers, restores
any replaced Android listener and finishes pending dismissals.

`Python/mobile/composition/presentation.py:notes_drawer_host` supplies the
current window, fold division, appearance, scroll clearance and privacy gate.
The host-created overlay remains registered with screen privacy, which detaches
private panels before showing the unlock screen.

```sh
python3 dev.py test mobile test_notes_drawers.py
python3 dev.py test mobile test_screen_privacy.py
```

Expect retained Files across fold changes, child scrolling and selection to
keep their own gestures, and no private overlays while locked. Use the
`notes-drawers` native probe for rotation and gestures on disposable devices.

## Data views and playlists

`dataview.py` discovers top-level fences and brokers bounded read-only requests. `dataview_script.py` implements an independent API subset in a disposable worker without network or writes. Trust defaults on. Generated content stays outside source/save baselines. Navigation retires workers. `test_text_editor_dataview.py` checks Chromium execution and source preservation. [Supported script surface](../user/user.md#json-data-views-in-notes-library)

`playlists.py` scopes stable entry IDs and positions to provider identity and library root. Credential-bound buckets are encrypted, with session memory for providers without a persistent key. Preserve unreadable buckets for recovery. Remove/repair stops an active entry. Locked continuation uses bounded prepared passages, a generic title and zero provider reads. Unlock and press Play to resume after exhaustion. `test_playlist_speech.py` checks locked seeking.

Desktop `desktop/settings/playlists.py` and mobile `mobile/settings/playlists.py`
use the same store for confirmed deletion across libraries and clearing locked
records. Both refresh unlocked credentials before deleting and keep source notes.
`test_notes_library_settings.py` covers cancellation, duplicate names, session-only
queues and credentials changing during confirmation; `test_settings_ui.py` covers
the mobile actions and privacy dismissal.
