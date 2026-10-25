# Notebook implementation and acceptance

## Brief elaboration and scope

The four RMDOC briefs originally proposed one-way Android/Boox native-ink export.
The October 25 request extends that scope to notebook import/editing, iOS, desktop
and page transfers. The implementation keeps the original four acceptance areas:
format correctness, input/recovery, multi-page binary export, and real-tablet
validation. Implemented source is not sufficient to mark all four briefs complete.

The new owner is `Python/features/notebooks`. Its desktop declaration contributes
a Notebooks page, document launcher and `.rmdoc` browser activation. Mobile adds
a destination between Home and Workspaces. The shared navigation host supports
up to seven destinations; no existing destination or reserved desktop tools menu
is removed. Numeric tab assumptions in affected tests use destination identities.

## Format and preservation boundary

`notebook.py` reads bounded ZIP members without extracting them. Traversal,
links, special entries, duplicate members, encrypted entries and oversized
archives are rejected. Exactly one document root is required. Notebook page lists
and `cPages` records are supported; deleted modern pages are omitted from the
editor. Unrecognized JSON fields and archive members remain opaque. Page changes
update ordering and page-count metadata; removed modern pages retain tombstones.
Copies get new page IDs and matching page sidecar names. PDF/EPUB-backed documents
are rejected pending background and redirection support.

`ink.py` preserves original v6 frames, using the vendored **rmscene 0.8.0** codec
for known native blocks. It retains imported point dynamics and native tool/color
IDs, emits native scene lines for new ink, and tombstones erased strokes while
retaining sequence links. New authors avoid existing author IDs. Scene order uses
CRDT order rather than physical frame order. Edited known stroke frames retain
extra fields; untouched frames are byte-preserved. Unknown objects, visible typed
text, highlights and text anchoring disable ink editing for the page. Empty root
text is preserved. Cross-notebook copies of unsupported objects are refused.

The model uses 1404 × 1872 page units with centered v6 X coordinates. Pressure is
normalized to 0–1 in the editor and written to the v6 0–255 field. Width is written
in quarter-units. Pressure-sensitive brush previews are approximate. Layer IDs,
visibility and supported brushes remain native scene data. Tablet rendering is
an independent acceptance gate.

The codec is MIT licensed. Its source (with one type-annotation namespace fix) and full license are under
`_vendor/rmscene`, pinned from the PyPI 0.8.0 distribution. It requires the declared
portable `packaging` runtime. Vendoring avoids rmscene's obsolete packaging<24
metadata conflicting with Briefcase's packaging>=24.2 build requirement.
See [rmscene upstream](https://github.com/ricklupton/rmscene) and the
[archive schema reference](https://github.com/go-go-golems/remarquee/blob/main/pkg/rmdoc/content.go).

## Editing and recovery

`workspace.py` owns commands, session undo/redo and the local repository. New and
imported notebooks receive independent local identities. The repository stores
an immutable source archive, content-addressed ink pages and an atomically
published recovery manifest. Ink commands update page blobs rather than rewriting
the complete archive. Structural edits additionally publish a new base containing
page resources. Publication precedes pruning of superseded recovery objects.
A process mutation lock and manifest revision check reject stale writers in
other windows. This is not a cross-process notebook collaboration protocol.

`canvas.py` supplies offline HTML/Canvas rendering and pointer input to Qt
WebEngine and native Toga WebViews. It records coalesced pointer samples, uses
stable page coordinates, distinguishes pen/touch, queues commands until the
host acknowledges them, and rejects navigation away from the local surface.
`bridge.py` validates the per-view origin token and monotonically ordered command
numbers. The page contains no remote assets. Completed commands are recoverable;
an interrupted in-progress pointer gesture is not a completed saved stroke.

Mobile uses existing native pick/export adapters. Imports copy selected bytes
under their scoped grant. Export remains binary and bypasses text-only Save As
validation. Private/encrypted document workflows are not redirected into durable
notebook storage. Desktop and mobile use the same archive and editing model.
The mobile source manifest includes the codec and notebook modules explicitly.

## Validation scope and remaining gates

Focused synthetic tests cover native brush/color/pressure fields, geometry,
erase/movement/undo/redo, page operations, opaque preservation, archive rejection,
failed writes, recovery and command origin/order. Wire-field checks supplement
readback through the upstream codec. The optional
`Python/tests/notebooks/independent_codec_probe.py` cross-checks synthetic archives
with the pinned MIT-licensed remarquee v0.0.14 Go reader, including all eight
brush IDs, multi-page ordering and erased-stroke tombstones. Its downloaded
modules and caches use manager scratch storage and are removed after the check. Host mobile tests cover destination order,
retained notebook state and importing without modifying originals. Native checks
exercise the actual WebView bridge, native ink export and on-device recovery.

Run the focused suites using `dev.py test desktop test_notebooks.py`,
`dev.py test mobile test_notebook_panel.py`, navigation regressions and lint.
The reusable native desktop probe is
`Python/tests/notebooks/notebook_canvas_probe.py`; it checks real mouse input,
Undo/Redo, page creation, recovery and export in manager-owned scratch storage.
Use the build manager's native Android/iOS plans; preserve its disposable-device
cleanup and retain evidence only under ignored test results.
`Scripts/mobile_payload.py` refreshes generated payloads with scratch rollback
when the two platforms build the same manager source snapshot. This keeps a
previous payload recoverable if preparation fails.

October 25, 2026 validation passed the 13 notebook model tests, two payload
rollback tests, four mobile notebook tests, navigation regressions, documentation
and feature-registry checks, and the repository correctness lint. The native
desktop probe passed pointer drawing, Undo/Redo, page creation, naming, layer
creation, recovery and export. The independent reader accepted the generated
eight-brush scenes and erasure tombstones. A complete Android emulator suite
(native UI, rotations and Python runtime) and iPhone simulator suite passed.
An earlier iPad suite passed, including independent windows and rotations.
The final naming-field and recovery changes additionally passed the focused
desktop probe and an isolated iPhone notebook QA app; the broad platform suites
were built before those final changes. Disposable apps/devices were removed.
The focused native entry point is `tests.logisticsmobile.notebook_probe`; it uses
synthetic private storage and publishes `notebook-result.json` in its cache.
It must run only in a separately identified QA application with owned cleanup.

Physical acceptance still requires writing with the Boox stylus, measuring the
reported pressure/palm behavior, exporting a synthetic notebook and importing it
on the actual reMarkable model/firmware. Select, move and erase exported strokes
there, add another stroke, export it again and inspect the result. Include page
add/reorder/copy, layers and current `cPages` ordering beyond one page. No hardware
result, universal firmware parity or complete arbitrary-document support is
claimed by the host tests. The four original briefs remain incomplete until
their mandatory native and physical gates have passing evidence.
