# Notebook implementation and acceptance

## Brief elaboration and scope

The four RMDOC briefs originally proposed one-way Android/Boox native-ink export.
The October 25 request extends that scope to notebook import/editing, iOS, desktop
and page transfers. The later October 25 clarification makes notebooks ordinary document types,
with no standalone navigation item on desktop, Android or iOS. Creation belongs
in New document, and opening/editing belongs in the existing file/document flows.
This supersedes earlier standalone-entry wording in the four Obsidian briefs.
The implementation keeps the original four acceptance areas:
format correctness, input/recovery, multi-page binary export, and real-tablet
validation. Implemented source is not sufficient to mark all four briefs complete.

The new owner is `Python/features/notebooks`. Its desktop declaration contributes
a document launcher and `.rmdoc` browser activation, without a feature page or
navigation destination. Android and iOS offer Notebook (.rmdoc) in the shared
New document chooser; local file activation opens a notebook document session
above the originating screen. The shared Documents lists, history, close adapters
and workspace restoration retain notebook identities and local recovery copies. The shared navigation host supports
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
in quarter-units. Imported v6 point widths are rendered directly without multiplying by thickness
scale or reapplying pressure. New-stroke brush dynamics are approximate. Layer IDs,
visibility and supported brushes remain native scene data. Tablet rendering is
an independent acceptance gate.

The codec is MIT licensed. Its source (with one type-annotation namespace fix) and full license are under
`_vendor/rmscene`, pinned from the PyPI 0.8.0 distribution. It requires the declared
portable `packaging` runtime. Vendoring avoids rmscene's obsolete packaging<24
metadata conflicting with Briefcase's packaging>=24.2 build requirement.
See [rmscene upstream](https://github.com/ricklupton/rmscene) and the
[archive schema reference](https://github.com/go-go-golems/remarquee/blob/main/pkg/rmdoc/content.go).

## Paper Pro / Move brush settings

`brushes.py` owns the nine native tool IDs, per-tool color choices, three width
labels, nominal widths and pressure/direction parameters. `drawing.py` consumes
this catalog in both desktop and touch presentations. Unsupported new
brush/color/width commands are rejected before saving; imported ink is not
restricted to the creation palette. The standard writing palette has nine colors;
Highlighter has yellow/green/pink/blue/orange/gray. Shader has gray and seven
hues (blue/red/green/yellow/cyan/magenta/orange), with no black or white choice.
Native green/yellow use IDs 10/13, distinct from legacy 4/3.
Orange uses editor choice -1, resolved before storage to native color 9 with an
RGBA override. Highlighter and Shader both use native color 9 plus RGBA.
Shader uses its own eight native RGB/alpha definitions, not the writing palette
with one uniform transparency. Reading, moving, copying,
undo and recovery preserve imported RGBA fields and original scene frames.

Thin/Medium/Thick select thickness scales 1/2/3. Nominal rendered widths are
tool-specific approximations, not measured firmware parity. New point widths are
computed once in page units, quantized to quarter-units and written to native
points. JavaScript preview and Python creation use the same catalog and equivalent
rules; the WebEngine probe compares them at all three widths. Imported v6 widths
already encode their dynamics and are never recomputed.

Pencil tools use deterministic grain; paintbrush has softer edges; calligraphy
uses stroke travel direction; highlighter uses darken blending; Shader uses
multiply blending and per-stroke alpha. Translucent/textured and calligraphy
previews incrementally accumulate opaque geometry in a separate mask. Only the
new segment bounds are recolored with texture/alpha, preventing dark seams and
work that grows with active-stroke length. Highlighter interior joins are filled
without changing its butt end caps. Fineliner and ballpoint paint incrementally
on the saved-scene canvas. No full saved-scene redraw occurs during ordinary
pen movement. Pending completed ink survives redraws until save acknowledgement.
Physical latency validation is still required. Tilt and exact speed-dependent
tablet textures are not simulated.

Grayscale converts resolved RGB (including RGBA overrides) to luminance in the
renderer. It never sends an editing command or changes the notebook.
It approximates readability, not firmware-specific dithering or compatibility.
Existing 1404 × 1872 page geometry remains unchanged.

Sources: the manufacturer's [writing tools](https://support.remarkable.com/s/article/Writing-tools)
explains tool behavior and the base palette; its
[OS 3.15 notes](https://remarkable.com/blog/remarkable-os-3-15-whats-new)
confirm Shader on reMarkable 2 and additional highlighter colors. Community
[Paper Pro field measurements](https://cable729.github.io/inkterop/docs/formats/remarkable/)
and [native RGBA examples](https://github.com/Scratchydisk/remarkable-rm#rgba-colour-discovery)
provide point-width and highlight-color evidence. The native
[Shader color definitions](https://github.com/ingatellent/xovi-qmd-extensions#changegreencolorqmd)
provide all eight per-color RGB/alpha values. These inform the implementation;
they do not certify Logistics exports on physical tablets.

`Python/tests/notebooks/brush_canvas_probe.py` runs the shared HTML at desktop and phone dimensions in
real Qt WebEngine, checking palette controls, three widths, model/preview width
equality, nine distinct raster results, direct native widths, grayscale isolation,
RGBA precedence, Shader overlap, live/completed pixel agreement and bounded
preview work after 2,000 samples. It saves contact sheets and concise results
under ignored `test-results/`. Run it with the desktop runtime and
`PYTHONPATH=Python:.`, passing `--output test-results/notebook-brushes/rendering`.
The model suite tests all offered brush/color/width combinations and RGBA through
move, undo, cross-notebook copy and recovery. Imported native eraser objects
are preserved read-only rather than drawn with
a fallback pen. Imported varying/zero point widths are respected even for
constant-width tool families. Exact size/texture calibration,
physical mobile stylus behavior and older-firmware import remain acceptance gates.

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

## E Ink drawing refresh

The canvas paints only incoming segments during ink movement, including
coalesced samples and the event itself when a browser returns an empty coalesced
list. Pointer-up captures its final position. Completed ink stays visible until
the host acknowledges saving; cancellation and lost capture discard the preview.
Full scene drawing remains for page changes, edits, resizing and acknowledgements.

Android packages `onyxsdk-device:1.3.5.3` from Boox's HTTPS Maven repository.
On Android 11 and newer, Boox initialization uses `hiddenapibypass:4.3`, as in the
[vendor demo](https://github.com/onyx-intl/OnyxAndroidDemo/blob/master/app/OnyxAndroidDemo/src/main/java/com/android/onyx/demo/SampleApplication.java).
Access exemptions are restricted to this process's `ViewUpdateHelper` symbols
and the vendor view update/invalidation methods. Initialization verifies distinct
DU/GC constants before initializing the SDK, and mode setters verify readback:
the SDK's boolean return alone can report success after blocked reflection.
`mobile/android/.../BooxRefresh.java` attaches only to notebook WebViews on
Onyx/Boox devices. It reads the previous view update mode and requests `DU` while
the stylus is down. Pen-up schedules restoration after 180 ms and a `GU` partial
update. A new stroke cancels that timer. Cancellation, window focus loss,
detachment and retirement restore the prior view mode without changing global or
application refresh preferences. Missing firmware support leaves ordinary
WebView drawing in use; failures are logged under `LogisticsBoox`.
The native source root, dependency and HTTPS repository are also refreshed in
reused Android projects by `configure_android_sources`.

This uses the vendor's [partial refresh API](https://github.com/onyx-intl/OnyxAndroidDemo/blob/master/doc/EPD-Screen-Update.md).
It does not yet use the separate [TouchHelper raw handwriting pipeline](https://github.com/onyx-intl/OnyxAndroidDemo/blob/master/doc/Onyx-Pen-SDK.md),
which needs its own input, brush, clipping and lifecycle validation on hardware.
The native notebook check measures 400 movement segments on a 2,000-stroke page
and requires zero full-canvas clears during movement, plus preview cleanup on
cancellation. This checks rendering work, not physical pen-to-pixel latency.

The focused Android entry point `tests.logisticsmobile.notebook_refresh_probe`
also requires the test-only Java source directory
`mobile_build/native_tests/android/notebooks` in its isolated QA build. Its fake
display driver exercises real Android events and timers: delayed restoration,
new pen contact, cancellation, focus loss, detachment, inherited update modes and
unsupported firmware. These checks and the populated-page check passed on an
Android emulator, alongside native desktop pointer drawing, Undo/Redo and
recovery. The QA app and owned emulator were removed.

The subsequent physical NoteAir5C check on Android 15 verified DU during injected
stylus strokes and restoration to GC after pen-up, on blank and 500-stroke pages.
Three interleaved old/incremental renderer trials on populated pages measured
median per-event drawing work of 9.5/0.2 ms and event-to-animation-callback times
of 45/27.4 ms. These are software timings from ADB stylus injection, not optical
measurements or a measurement of the physical digitizer. The separate
`tests.logisticsmobile.boox_drawing_probe` entry point requires an isolated QA
build and a recorded `canvas_baseline.py` fixture from the earlier source
revision. Its ready file supplies screen coordinates to the host stroke driver;
completed trials retain timings, pointer types, saves and native mode readbacks.
On Boox, the test package may need enabling after the launcher's delayed automatic
freeze. Use a distinct FileProvider authority as well as a distinct app ID.
The test app was removed afterward and only the main Logistics package remained.
Physical pen-to-visible-pixel latency still requires external camera measurement.

## Mobile persistence and export

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
(native UI, rotations and Python runtime) and iPhone/Duo simulator suites passed.
An earlier iPad suite passed, including independent windows and rotations.
The final naming-field and recovery changes additionally passed the focused
desktop probe and an isolated iPhone notebook QA app; the broad platform suites
were built before those final changes. Disposable apps/devices were removed.
The focused native entry point is `tests.logisticsmobile.notebook_probe`; it uses
synthetic private storage and publishes `notebook-result.json` in its cache.
It must run only in a separately identified QA application with owned cleanup.

The subsequent desktop/edge-case review adds isolated registry and document
launcher coverage: the optional desktop feature contributes an RMDOC
launcher and file activation, and New creates a notebook directly. Retired canvas
events cannot reach a replacement notebook. Mobile imports and commands reserve
their busy state before yielding, reject stale WebViews and retire replaced
canvases. Failed imports return failure to Workspaces; failed acknowledgements
offer reopening of the saved copy. Expanded controls scroll within half the view.
Template substitutions precede user state insertion, so titles containing marker
strings cannot corrupt the editor. Oversized commands report an error without
advancing the bridge sequence. New ink must remain readable before recovery is
published; limits are 100,000 points per stroke and 1,000,000 points per page.
Empty damaged scenes, invalid thickness scales and nested groups are preserved
read-only. Invalid page indices are rejected before mutation, and a cleanup
failure after manifest publication does not roll back an already-saved edit.
The review passed 23 desktop/model tests and eight mobile workflow tests,
correctness lint, the real desktop canvas probe and focused Android/iPhone native
checks, including QA app and disposable-device cleanup.
These checks supplement rather than replace the earlier broad native suites.

The document-integration revision removes the desktop page contribution and mobile
Notebooks destination. Desktop notebooks use the existing document host and type
chooser; mobile notebook sessions use the shared Documents inventory/history,
local-folder creation picker, close/return adapters and restoration manifest.
Legacy mobile scene destinations migrate to Documents. Imported notebook files
remain unchanged; local working copies retain ink and are exported explicitly.
Qt Quick Python type bindings are loaded before the desktop WebEngine canvas to
avoid PySide6 6.12 wrapper identification crashes under application event filters.

This revision passed 23 desktop notebook/model tests, 17 mobile notebook/creation
tests, 95 mobile navigation regressions, 28 desktop document-workspace tests,
eight mobile packaging tests, documentation layout and correctness lint. The
native desktop probe now embeds the notebook in Documents and checks that
notebook naming does not rename the host. Focused native iPhone and Android QA
checks cover New document → Notebook, local creation, ink/page/layer editing,
recovery, close/reopen and returning through Documents without leaving the canvas
command queue waiting. Temporary QA apps, disposable devices and crash-probe
scratch directories were removed using their owning lifecycle helpers.

Physical acceptance still requires writing with the Boox stylus, measuring the
reported pressure/palm behavior, exporting a synthetic notebook and importing it
on the actual reMarkable model/firmware. Select, move and erase exported strokes
there, add another stroke, export it again and inspect the result. Include page
add/reorder/copy, layers and current `cPages` ordering beyond one page. No hardware
result, universal firmware parity or complete arbitrary-document support is
claimed by the host tests. The four original briefs remain incomplete until
their mandatory native and physical gates have passing evidence.

## Provider-backed notebook documents

`storage.py:NotebookDocument` owns the format draft and receives a generic
`services.documents.storage.DocumentResource` plus an optional recovery adapter.
The canvas edits the model through its checkpoint callback; it does not resolve
crypt names, credentials or local paths. The host supplies ordinary recovery only
when the resource's persistence policy allows it. Private drafts remain in RAM.

Save publishes verified bytes with the original revision, while failed saves keep
the draft and baseline. Save As uses the existing picker and retargets the editor;
explicit export creates a separate copy and requires a plaintext confirmation for
private sources. Desktop notebook WebEngine profiles are off the record. Mobile
notebook resources have independent provider access, transient workspace sessions,
credential revocation/lock guards and source-aware Move/Rename adoption. Ordinary
source bindings preserve recovery without overwriting a source changed elsewhere;
recovered drafts can choose a new destination with Save As.

See [document storage and the action matrix](../../../development/document-storage.md)
for host policy, current format/platform limits and cloud boundaries. Focused
regressions are `test_document_storage.py`, `test_notebook_resources.py`,
`test_notebook_storage.py`, `test_document_creation.py` and the optional real native
bridge checks in `test_mobile_localcrypt_native.py`. The focused native driver is
`mobile_build/validation/document_storage_tools.py`; it uses the existing prepared
projects and bridge helpers, manager-owned scratch and disposable Android/iOS
devices, with evidence saved before teardown. Physical Boox pen quality and actual
reMarkable editability remain separate acceptance gates.
