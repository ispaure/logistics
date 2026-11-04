# Notes Library feedback review

This review covers the five-part desktop/mobile feedback list from November 2,
2026. The starting branch already contained implementations of all fifteen items
in part 2. The review checked their current owners and focused regressions, then
completed the remaining Markdown presentation and loading work.

## Requested behavior

| Request | Implemented behavior and verification |
| --- | --- |
| Part 1: video embeds | Wiki and standard Markdown video embeds have inline controls in desktop reading/formatted editing and mobile HTML reading/formatted editing. Desktop verification decodes actual muted H.264 frames; mobile host checks verify HTML and exact source preservation. Source mode retains authored syntax. |
| Part 1: all file types | Files panes show every non-dot-prefixed file type, including extensionless files. Miscellaneous files can be moved and route through ordinary document viewers. Hidden configuration remains excluded. |
| Part 1: library titles | Container/session titles use the root folder name. Desktop LocalCrypt roots use the logical connection name rather than the physical storage directory. Mobile document chrome retains the current filename. |
| Part 2.1: folder browsing speed | Folder expansion lists metadata only. Same-named landing notes use bounded provider batches rather than opening document bodies. Real LocalCrypt provider checks cover those batches. |
| Part 2.2: desktop entry icons | Files, folders and folder notes have distinct entry artwork; desktop uses the same artwork as mobile and refreshes it after palette changes. |
| Part 2.3: mobile disclosure | Folder expansion uses a separately labelled 48-point disclosure control. The filename can open the folder note independently. |
| Part 2.4: Notes Back behavior | Opening a document from the drawer remembers its browsing return state. System Back restores that drawer before leaving the library. |
| Part 2.5: reader Back behavior | Published comic, PDF and EPUB page visits can be retraced. Video retains screen-level Back behavior. EPUB checks wait for actual page publication before adding a visit. |
| Part 2.6: favorites | Open-file menus expose favorites. References retain Notes Library context, and favoriting through another viewer replaces the opening mode. |
| Part 2.7: desktop recents | The landing page displays recent files below favorites. |
| Part 2.8: private references | Session-only favorite/recent references use credential-encrypted buckets and stay hidden without matching unlocked credentials. Revoked landing rows are retired. |
| Part 2.9: library discovery | Workspace folder browsing has no library-choice prompt. Mobile Documents discovers local/LocalCrypt libraries through `.obsidian`, at most two folders down, within unlocked storage. |
| Part 2.10: search display | Desktop results use Name, Type, Size and Path columns, with filename-first names. Mobile names remain compact. |
| Part 2.11: search activation | Result activation retains provider-relative identity. Keyboard and real double-click checks cover desktop library/provider search. |
| Part 2.12: file operations | Library file/folder actions expose move, copy and delete where supported. Read-only providers keep mutation controls disabled or absent. |
| Part 2.13: credential password changes | Desktop credential settings confirm a new password twice, verify re-encryption before replacement and preserve the original package on failure/cancellation. |
| Part 2.14: split document tabs | Desktop library document groups retain independent drafts and resources, allow left/right placement and remain scoped to their library. |
| Part 2.15: drag moves | Desktop/mobile file and folder drops use provider moves, with an explicit library-root target. Collisions, descendant moves and overlapping operations preserve the source. |
| Part 3: welcome actions | Desktop uses a heading, short instruction and compact create action. Open Document appears when the folder sidebar is hidden and reveals it; mobile follows the same visibility rule. |
| Part 4: linked headings | Desktop applies heading size to link fragments, fixing `# # [[Art]]` and `# # [[Tech]]`. Native HTML checks confirm links remain inside heading tags. Source text and navigation targets are preserved. |
| Part 5: opening feedback | Desktop/mobile share note finding and reading stages. Hosts report finding, reading and embedded-media preparation separately. Desktop preloading is bounded to 128 resource references. |
| Part 5: missing custom view | Exact custom-view paths win; an unambiguous component-by-component case match is accepted next. This resolves `Dataview` versus `dataview` on LocalCrypt without recursive discovery or leaving the library. Real encrypted-provider tests cover the reported path form. |

## Review passes and storage lifetime

The first pass compared the requested behavior with implementation, history and
focused desktop/mobile regressions. It found duplicate file filtering, a
miscellaneous-file move restriction, heading-link sizing, generic desktop loading
feedback, and stale tests that still assumed the previous file-row layout.

The integration pass checked provider identity, revocation, source preservation,
resource limits and cleanup. Video embeds use the existing capability-URL range
transport without decrypted staging files. Each document admits at most eight
video sources. Closing, private-content retirement, Save As and cancelled
standalone preparation close owned streams; hiding native players pauses them.
Each image render receives a fresh raster budget. The review also corrected
logical LocalCrypt root titles and ensured bundled mobile manifests include the
new service owners and entry artwork.

Focused checks cover Notes Library documents/tabs, LocalCrypt file operations,
Dataview reads, catalog encryption, credential password changes, Android Back
dispatch, comic/EPUB visits, reader lifetime, mobile Markdown editing and shared
Markdown image/heading rendering. These host checks are not certification of
physical Android/iOS gesture delivery, native WebView codecs or device layout.
No release gate or full-project test round is implied by this review.

## Follow-up media refresh review

Cached video streams now validate their source revision before reuse. Replacing
a video retires the old content/transport and admits a fresh stream; deleting it
or revoking access retires cached playback instead of returning a stale URL.
Unchanged videos keep their existing stream. Focused regressions verify those
lifetimes and read replacement bytes through the new playback URL. Existing
LocalCrypt media and mobile library checks cover integration with the shared
desktop/mobile callback.

## Reusing Markdown references

Document-owned raster bytes are reused across mobile reading and formatted
editing, with provider access and revision checks before reuse and bounded RAM.
Replacement bytes refresh automatically; removed references stop being requested
by the new render, and closing the document clears retained media. Library link
resolutions retain their directory dependencies: changed names invalidate the
result, including a newly created nearer target. Providers without reliable
local directory stamps continue using live resolution. Desktop mode switches
already reuse their prepared resource map and unchanged formatted document.

The media regressions cover repeated renders, replacement/deletion, link
precedence changes, revocation, cancellation and video stream retirement. Mobile
Notes Library mode regressions cover the existing navigation/authoring flow.

## Editor preparation feedback

Mobile Notes Library retains the published reader beneath its existing loading
panel while preparing an editor. The panel says “Preparing for editing…” and
Cancel restores the reader and invalidates the pending publication. Regular
provider Markdown and switching back to formatted library editing also expose
Cancel during worker preparation. Drafts survive cancellation; late worker
results cannot replace a newer view. Desktop already retains the unchanged rich
editor and RAM resources when switching modes, avoiding this preparation step.
Host regressions exercise slow preparation, cancellation and superseding views.

## Separate Rename and Move

Desktop and mobile now expose separate Rename and Move actions. Rename accepts
one name and uses the existing provider move workflow. Move keeps that name and
browses existing folders through the hosts’ existing browser controls, backed by
a shared library-rooted folder projection. The projection hides files, hidden
configuration, the source folder and its descendants. Picker cancellation and
superseded callbacks preserve the source, draft, current document and drawer.
Collision checks and history updates remain owned by the existing move workflow.

The Workspaces scheduled-picker callback crash was fixed concurrently in the
mobile action-menu owner; its destination-workflow regressions pass. Notes uses
the same browser controls with library-local selection and move publication.
Focused mobile mode/panel checks cover browsed moves and cancellation. Desktop
checks exercise the real folder dialog, rename, provider media, encrypted storage
and move workflows. These are host checks, not physical Android/iOS validation.

Two final review passes checked items 3–5: the first traced reference lifetimes,
loading/cancellation and separate action entry points; the second checked
provider boundaries, stale callbacks, resource cleanup, platform scope and tests.

### Folder-browser host boundary

`NotesHost.folder_browser` supplies the mobile Move picker’s native browser.
The application composition layer owns its implementation and disables persistent
indexing; the feature supplies only library-rooted folder snapshots and callbacks.
The move/cancel regression checks that the injected factory is used and that no
local or resource index callback remains attached.
