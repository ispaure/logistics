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
labels, nominal widths and pressure/direction parameters. `assets/drawing.js` consumes
this catalog in both desktop and touch presentations. Unsupported new
brush/color/width commands are rejected before saving; imported ink is not
restricted to the creation palette. The standard writing palette has nine colors;
Highlighter has yellow/green/pink/blue/orange/gray. Shader has gray and seven
hues (blue/red/green/yellow/cyan/magenta/orange), with no black or white choice.
Native green/yellow use IDs 10/13, distinct from legacy 4/3.
Orange uses editor choice -1, resolved before storage to native color 9 with an
RGBA override. Highlighter and Shader both use native color 9 plus RGBA.
Shader uses its own eight native RGB/alpha definitions, not the writing palette
with one uniform transparency. Swatches composite that alpha over white.
Reading, moving, copying,
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
renderer and swatches. It never sends an editing command or changes the notebook.
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

`Python/tests/notebooks/brush_canvas_probe.py` runs desktop and mobile HTML in
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

Desktop **New** opens a `NotebookDocument` without a storage resource or recovery
repository. Edits mark this in-memory draft dirty; the first explicit Save
chooses its destination. Cancelling Save retains the draft, and closing a dirty
draft uses the ordinary Save/Discard/Cancel guard. Untouched blank drafts close
without a prompt.

`editor.py` owns commands and session undo/redo. `recovery.py` owns the local
repository and observed manifest revisions, kept outside the format model. New and
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
Desktop opts into `editor_html(..., desktop=True)`. `assets/desktop.html`, `desktop.css` and `desktop.js` own a
horizontal drawing toolbar, brush/color/width controls, layer popovers and footer;
`icons.py` supplies original inline SVG glyphs shared with mobile. `ui/menus.py`
creates the source window's File/Edit/View/Page menus, published by the existing
workspace menu host. Standard QAction shortcuts use WidgetWithChildren scope.
Menu commands enter the browser command queue through `notebookCommand`; local
view/tool settings use `notebookUI`. WebEngine delegates command shortcuts it
retains to that same queue; Qt-consumed shortcuts never reach the browser.
Undo/Redo in focused text fields edits the field rather than notebook ink.
The tab/window title remains the document title; the canvas title is hidden.
Native desktop coverage checks drawing, menu dispatch, the real Save shortcut,
brush shortcuts, toolbar hiding and default fit-page bounds at 720/1280-pixel widths.
Fit Page accounts for both viewport dimensions, padding and page notices;
Fit Width and fixed percentages remain available. Desktop Zoom In/Out use Qt's
platform key bindings plus the unshifted equals alias; Ctrl/Command+0 restores
Fit Page. WebEngine key fallback and Ctrl/Command+wheel use the same bounded
10–400% canvas zoom controller, preserving the page coordinate under the pointer
(or the viewport center for keys/menus) without changing WebEngine zoomFactor.
The native probe checks real zoom keys and modified wheel events, pointer
anchoring, both DOM modifier flags, ordinary-wheel behavior and numeric bounds.
Regression tests cover menu publication, owner dispatch and page/history bounds.

Desktop enables queued continuous ink. Successful stroke commands acknowledge
only the new durable stroke through `notebookStrokeUpdate`, updating native menu
history without serializing or replaying the complete scene. Structural edits
and errors still return full state; in-progress pointer gestures defer received
acknowledgements until release/cancellation. Save and history commands follow
pending ink in the same ordered queue.

`Python/tests/notebooks/notebook_desktop_stress_probe.py` exercises nine brushes,
rapid native mouse input with delayed acknowledgements, repeated undo/redo,
actual file publication and failed-save recovery, cancelled save/close,
Save As retargeting, multi-page reopening, zoom redraws and a 40,000-point page.
Its large-page check verifies that ink does not invoke full-scene drawing and
that an acknowledgement received mid-gesture is deferred without losing ink.
Run with the desktop runtime and `PYTHONPATH=Python:.`, passing
`--output test-results/notebook-desktop-stress`. Documents and storage fixtures
use manager scratch; retained reports include exact source hashes and observed
frame timings. These timings describe this host, not physical stylus latency
or Windows/Linux native acceptance.

`bridge.py` validates the per-view origin token and monotonically ordered command
numbers. The page contains no remote assets. Completed commands are recoverable;
an interrupted in-progress pointer gesture is not a completed saved stroke.

## Mobile editor presentation

`mobile/surface.py` enhances the default offline canvas with a floating top icon
strip and separate writing-tool, layer, page and notebook sheets. The document
viewport fills the editor; no layout space is reserved for persistent title,
status or navigation rows. A hide-tools state leaves one restore button and
preserves drawing settings and scroll position. Routine status lives in the
notebook sheet; errors also appear in a dismissible alert. It reparents
existing controls, preserving the common command handlers and model values.
Original SVG nibs and glyphs come from `icons.py`, shared with desktop.
Brush cards, per-tool color swatches and three stroke samples follow the current
model choices. Sheets contain keyboard focus, restore focus to their opener,
and leave the background inert while open. The floating dock remains compact in
portrait and landscape; drawing actions have at least 44 × 44 CSS-pixel targets.
The mobile source manifest includes both presentation and icon modules.

The toolbar stays between the existing corner controls on wide views; below
420 CSS pixels it occupies a second floating row to avoid overlap. Selected
brushes have a dark fill, contrasting labels and a check mark, and the current
nib button carries an ink-color indicator. Palette discs use explicit SVG circle
paint with native button appearance disabled and forced-color adjustment scoped
to the discs. This preserves semantic ink colors when the app's E Ink CSS
rewrites ordinary backgrounds. Grayscale preview applies to the document while
the palette remains chromatic. Pages/Layers shortcuts use bounded 22-pixel SVGs
and labelled 52-pixel touch buttons, preventing SVG intrinsic dimensions from
expanding the action panel.


The reusable `Python/tests/notebooks/notebook_mobile_ui_probe.py` checks this
HTML in a native Qt WebEngine window at phone/tablet dimensions, including
320-pixel portrait and short landscape. It checks actual browser geometry,
brush/color/width selection, panel dismissal/focus, pointer drawing, Undo/Redo,
page and layer creation, naming and recovery. Run with the project interpreter,
`PYTHONPATH=Python:.`, and `--output` under ignored test results. It uses manager
scratch storage for synthetic notebooks and cleans up its temporary window.
The October 25 redesign passed the browser probe at six sizes, including a
320 × 390 constrained viewport, full-height document geometry, hide/restore,
error visibility and settings preservation, plus nine mobile
notebook host tests, eight packaging tests, five documentation checks and focused
lint. A subsequent focused iPad simulator run passed the native `WKWebView`
checks described below; Android's redesigned native surface and physical stylus
behavior remain separate acceptance scopes.

The subsequent top-toolbar iteration passed six browser viewport sizes with
normal and injected E Ink styling, plus ten mobile notebook host checks and
focused lint. Native iPad QA passed with iOS **Increase Contrast** enabled,
including the top/corner geometry, selected brush label contrast, native writing
and highlighter palette values, compact Pages/Layers SVG bounds, and current
save/close-to-Home/reopen behavior. Native screenshots were inspected after
waiting for WebKit presentation. Pixel inspection after color-profile conversion
confirmed all six highlighter fills in normal and E Ink-styled palette captures.
The QA app and owned simulator were removed. These remain simulator/software
checks, not physical tablet color or stylus calibration results.

## iOS pen input and validation

The iOS host uses Toga's `WKWebView` and the common Pointer Events canvas, rather
than `PKCanvasView`/PencilKit. WebKit supports pen/touch pointer events and
pressure; see [WebKit's Pointer Events introduction](https://webkit.org/blog/9674/new-webkit-features-in-safari-13/).
The common pointer handler cancels an existing finger-pan state at pen contact,
so an already-resting finger cannot scroll the page during that pen stroke.
Finger drawing remains an explicit option. No PencilKit system picker, native
Pencil double-tap/squeeze mapping or tilt-dependent brush response is claimed.

`native_tests/tests/logisticsmobile/notebook_pointer_checks.py` exercises pen
pressure, coalesced samples, finger/pen arbitration, pointer cancellation,
capture loss and optional finger drawing in the real WebView. The test stubs
capture for synthetic events, restores all canvas state, and records the native
backend and `WKWebView` identity on iOS. The desktop browser probe reuses those
checks. Synthetic events do not validate a digitizer, physical pressure reporting,
palm rejection or pen-to-pixel latency.

Run the focused native iPad check using the project interpreter:

```sh
.venv/bin/python -m mobile_build.validation.document_storage_tools ios \
  --probe notebook --family iPad --increase-contrast \
  --output test-results/notebook-ios-pointer/native
```

The existing focused build helper stages current allowlisted sources, builds a
separate notebook QA bundle in manager scratch storage, uses a manager-owned
iPad simulator, saves evidence outside scratch, then uninstalls the QA app and
removes only that owned simulator. The main Logistics app and personal devices
are outside this check. Use `--family iPhone` to check the same mobile surface on
a phone; iPhone testing does not establish Apple Pencil hardware support.

The October 25 focused iPad simulator run passed the actual Toga iOS backend
and `WKWebView` identity checks, synthetic pen pressure (0.2/0.4/0.8), coalesced
samples, finger-pan arbitration, cancellation/capture loss, optional finger
input, compact controls, drawing, page/layer operations, naming, recovery,
archive readback and close/reopen/return acknowledgement. The isolated QA app
and owned simulator were removed. The probe now waits for native/background
initialization before creation and for the JavaScript queue acknowledgement
before testing a retained editor. Earlier failed test attempts remain evidence
of those fixture timing failures, not passing runs. Physical Apple Pencil
pressure, palm behavior and pen-to-pixel latency are still unverified.

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


## Mobile drawing and document actions

The mobile canvas enables ordered continuous ink: completed strokes remain
painted while their native checkpoint runs. Successful stroke acknowledgements
carry only the normalized new stroke and save status; structural operations and
errors still replace the full state. An acknowledgement arriving during a pen
stroke waits until pen-up/cancellation, preserving live mask geometry. Queued
strokes are included when zoom or another operation redraws the page.

Close acknowledges the canvas command before requesting the shared save/discard
guard, so cancelling cannot leave JavaScript permanently busy. iOS uses the host
reader's native X in place of Back and hides the duplicate canvas close button.
Its callback enters the same drawing queue before closing. Android retains one
canvas X. File actions reveal the retained provider source and confirm deletion
of a source plus recovery, or a recovery-only draft. Deletion uses the provider's
revision guard and refuses a source changed since opening. Page deletion uses a
native confirmation rather than a WebView JavaScript dialog.

The notebook native probe exercises bursts of twelve strokes with every brush,
ordered native acknowledgements, undo/redo and recovery after each burst, pointer
cancellation and coalesced pressure. Its document-action checks present native
decisions, cancel closing and resume drawing, reveal the file, and cancel/confirm
file and draft deletion. These software checks do not measure physical Pencil
latency or certify hardware palm rejection.

## Notebook refactor boundaries

`notebook.py`, `ink.py` and the vendored codec retain archive and scene ownership.
`editor.py` applies validated model commands transactionally; `recovery.py` publishes
per-page checkpoints and guards observed revisions. Recovery manifests keep schema 1.
Source reloads explicitly adopt the revision observed by the recovery repository;
notebook objects carry no persistence revision attributes.

`protocol.py` defines model versus host command names, action shape validation,
document status and full-state/stroke acknowledgement serialization. Ordered bridge
envelopes are consumed before action validation so invalid actions receive an error
acknowledgement through the host. A full response handles structural edits, errors
and cancellation; a stroke delta avoids replaying the whole page. Close releases
the queue before presenting the native save guard.

`canvas.py` composes explicit offline assets: queue/acknowledgements in `queue.js`,
input and gestures in `input.js`, viewport rendering in `viewport.js`, brush geometry
in `drawing.js`, and initial event wiring in `boot.js`. Desktop and mobile have
separate presentation assets. Mobile controls use `data-action` identities rather
than matching JavaScript handler source. The owning mobile manifest includes every
asset; staging permits JavaScript, CSS and HTML alongside Python/native sources.
The generated document still makes no external asset requests. User state enters
the completed template last, with HTML-significant characters escaped.

Each canvas owns a fresh `Bridge`; retirement rejects further commands and stops
awaited mobile continuations from touching a replacement surface. Desktop save
completion checks its captured canvas and closes resources returned to a retired
surface. Platform adapters retain native dialogs, pickers, WebView and refresh
lifetimes. Shared document services continue to own resource/storage policy.

The refactor's focused regressions cover malformed-action rollback, independent
recovery identities and stale revisions, recovery reload ownership, retired
canvas commands/awaits, stale desktop save completion and shared status responses.
Existing model/resource suites retain opaque-member, native scene, private-storage
and failure-publication coverage. The desktop stress probe checks delayed
acknowledgements, Save/Save As cancellation, failed publication/retry and large-page
rendering; mobile browser and brush probes cover responsive controls and raster
parity. The independent pinned Go reader cross-checks multipage exports and erasure
tombstones. Focused Android emulator and iPad WKWebView notebook QA additionally
exercise handwriting bursts, close/cancel/resume, file actions and recovery.
These checks establish software behavior, not physical stylus or reMarkable
firmware acceptance. QA applications and manager-owned test devices are removed.
