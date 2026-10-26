# Notebook implementation and acceptance

The remaining physical procedure is [notebook hardware acceptance](hardware-acceptance.md).

Desktop save/export progress uses commonUtils' shared compact `OperationProgress`
footer below the canvas. The canvas takes the workspace stretch; progress stays
in one row with the status message, meter and Cancel control. Notebook library
messages use the shared `StatusLine` at the bottom of the listing.

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

Deletion is composed through `NotebookDocument.delete`: revision-checked source
removal belongs to `services.documents.storage.DocumentResource.delete`, and
ordinary draft removal belongs to `recovery.Repository.delete`. The mobile panel
keeps confirmation, window guards and session retirement, without raw file I/O.
Private notebooks have no ordinary recovery repository. Host regressions cover
cancel, changed sources and ordinary/private deletion.

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

Pointer samples and pressure are captured immediately. Desktop preview painting
is batched to animation frames; mobile paints delivered pen batches immediately.
Pen-up flushes the remaining samples before queuing
the command; cancellation retires the scheduled paint. Masked brushes commit only
their painted rectangle with the brush's blend mode, avoiding a second vector
replay or a full-page bitmap copy. Resizing still reconstructs ink from the model.

`Python/tests/notebooks/notebook_desktop_stress_probe.py` exercises nine brushes,
rapid native mouse input with delayed acknowledgements, repeated undo/redo,
actual file publication and failed-save recovery, cancelled save/close,
Save As retargeting, multi-page reopening, zoom redraws and a 40,000-point page.
Its large-page check verifies that ink does not invoke full-scene drawing and
that an acknowledgement received mid-gesture is deferred without losing ink.
Three paced 200-move gestures must stay below an 80 ms browser frame-gap guard.
The large page additionally exercises undo/redo, zoom, Save As, continued editing
and a second verified Save. Pixel checks compare live and committed brushes over
colored ink, and input-burst checks retain every pressure sample while batching
painting. The synchronous probe drains retired WebViews before measuring a new
renderer, and pixel fixtures allocate only their ink bounds at high DPI.
Run with the desktop runtime and `PYTHONPATH=Python:.`, passing
`--output test-results/notebook-desktop-stress`. Documents and storage fixtures
use manager scratch; retained reports include exact source hashes and observed
frame timings. Timings describe the tested runtime rather than physical stylus
latency. The probe waits for the native input widget and canvas presentation
after reopening, then observes delivery of each pointer release before checking
bridge idleness; Windows can process a JavaScript query ahead of native input.

For the existing Build Deployment Manager guests, the Logistics Windows/Linux
backend commands accept `--native-notebooks` alongside a focused `--pattern`.
After desktop dependency preparation, this runs `notebook_platform_probe.py`:
the drawing/save stress probe, menu/zoom probe and brush pixel probe, using the
Windows Qt backend or Linux X11 backend. Linux without a desktop session uses
an owned `xvfb-run` display rather than Qt's offscreen plugin. Reports are collected
with the manager's guest evidence before its temporary workspace is removed.
Check that guests are idle before reserving them. Virtual mouse/frame timings
do not establish physical pen latency or coverage of other guest architectures.
Windows defaults to the normal app graphics configuration; it does not force
software Chromium rendering. The standalone driver accepts `--rendering software`
for a complete software backend or `--rendering chromium-software` for the previous
Chromium-only software configuration. These are explicit graphics diagnostics;
retain their failures separately from normal-renderer acceptance. Headless Linux
uses the complete software configuration with X11. The stress report separates an
unpaced 500-move input flood from the three paced gestures; the frame-gap guard
applies to paced input rather than a synthetic flood that can block Qt's event loop.

The Windows backend also accepts `--notebook-rendering native|software|chromium-software|warp|all`
with `--native-notebooks`. Repeat `--notebook-probe` with a check name to focus
on selected probes; the default still includes the page-two memory check. The
standalone driver exposes the same selector as `--probe`. `warp` uses Microsoft's CPU Direct3D renderer in both
Qt and Chromium; it is an explicit diagnostic, not the application's default.
`all` includes WARP only on Windows. Reports record the actual PySide version,
canvas context attributes, small-page timing and three paced large-page gestures.
A failed latency guard is reported after history, zoom and verified saving have
been exercised, so performance failures do not conceal functional coverage.

Forced software acceptance remains unresolved on the manager's Windows ARM64
VM with x64 Python/Qt under emulation. Both Qt 6.12 and an isolated 6.11.2
comparison reproduced long frame gaps; WARP reduced them but did not reliably
meet the 80 ms guard. Earlier default-renderer runs passed at 33–50 ms; the latest
visible-console retest reached 83.3 ms and narrowly missed the same guard. The
foreground check verifies the native Windows foreground PID matches the editor.
The foreground-verified software run still reached 700 ms, and the final WARP
run timed out waiting for JavaScript. These runs used the frozen source from the
preceding memory acceptance; subsequent shared UI changes are outside their scope.
Experimental canvas
backing, blend-layer and raster-flush changes were removed because they did not
resolve the stall. A native Python 3.12.2 ARM64 probe installed the locked wheels
but could not import `QtWebEngineCore`: native Windows ARM64 WebEngine is absent
from the official binaries ([Qt Windows support](https://doc.qt.io/qt-6.12/windows.html)).
These results do not establish behavior on native x64 Windows hardware or prove
whether Qt, emulation or their graphics interoperation is the ultimate cause.

`bridge.py` validates the per-view origin token and monotonically ordered command
numbers. The page contains no remote assets. Completed commands are recoverable;
an interrupted in-progress pointer gesture is not a completed saved stroke.

## Mobile editor presentation

`mobile/surface.py` enhances the default offline canvas with a floating top icon
strip, an anchored notebook dropdown, and separate writing-tool, layer, page
overview and view/input sheets. The document
viewport fills the editor; no layout space is reserved for persistent title,
status or navigation rows. A hide-tools state leaves one restore button and
preserves drawing settings and scroll position. Routine status lives in the
notebook dropdown; errors also appear in a dismissible alert. It reparents
existing controls, preserving the common command handlers and model values.
Original SVG nibs and glyphs come from `icons.py`, shared with desktop.
Brush cards, per-tool color swatches and three stroke samples follow the current
model choices. Sheets contain keyboard focus, restore focus to their opener,
and leave the background inert while open. The floating dock remains compact in
portrait and landscape; drawing actions have at least 44 × 44 CSS-pixel targets.
The mobile source manifest includes both presentation and icon modules.

The close button, drawing tools and notebook actions share one floating row.
Spacing contracts down to 320 CSS pixels while retaining 44 × 44 targets.
Hide tools lives in the notebook actions dropdown; iOS hides the canvas close
button when the native reader supplies one. Selected
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
320-pixel portrait, the former 419/420-pixel breakpoint and short landscape.
It checks a single row with non-overlapping 44-pixel targets, both with a canvas
close button and with the iOS native-close flag. It checks actual browser geometry,
brush/color/width selection, panel dismissal/focus, pointer drawing, Undo/Redo,
page and layer creation, thumbnails, insertion after the current page and recovery. Run with the project interpreter,
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

### Android history and mobile page navigation

`NotebookInput.java` requests unbuffered dispatch on native pen contact and
forwards each MotionEvent history position/pressure and current sample to the
canvas in order. Native coordinates are mapped using the current WebView size.
The canvas suppresses duplicate trusted Chromium pen events, while buttons and
finger input keep ordinary WebView dispatch. Cancellation, lost focus, detachment
and retirement discard unfinished ink. No device polling-rate setting is changed.
See Android's [advanced stylus input guidance](https://developer.android.com/develop/ui/views/touch-and-input/stylus-input/advanced-stylus-features).

Mobile paints each delivered sample batch immediately and requests a
desynchronized 2D context; unsupported browsers may ignore that hint. Desktop
retains frame batching. The view-scoped Boox DU/quality lifecycle below remains
in use. This reduces pipeline waits, without claiming optical latency parity
with native handwriting apps or using the separate vendor raw-drawing pipeline.

Horizontal single-finger swipes turn pages when the page fits the viewport width.
Zoomed views retain panning; vertical, cancelled, multi-touch and out-of-range
gestures do not turn pages. The overflow menu is an anchored dropdown. Pages
Overview requests ink-only SVG previews in batches of 16, each bounded to 256
strokes and roughly 2048 sampled points. Hidden layers are excluded. Preview
requests do not edit page state or save; templates/unsupported content are labelled
as outside the thumbnail scope. Direct page navigation and Add page use the same
ordered command bridge; Add page inserts at `editor.index + 1`.

The calligraphy profile uses an original fixed 45-degree elliptical nib with
quarter-unit perpendicular widths shared by preview and the native codec. Its
slant depends on stroke direction, never hardware tilt. Stored widths are used
without applying pressure again when rendering imported ink.

The focused `notebook_input_probe` passed on the physical NoteAir5C: 22 injected
native pen history samples became one stroke, pressure 0.2–0.8 produced widths
1.25–5.75, and the canvas top matched the zero cutout inset. Synthetic swipe
guards, four thumbnails, direct page navigation and insertion after the current
page passed. The temporary QA package was uninstalled, leaving the main app.
These are software/native event checks, not digitizer or optical measurements.
Run the owned build/cleanup helper with `--probe notebook-input --device SERIAL`
for this focused connected-Android check. Browser checks cover six phone/tablet
sizes and live/saved brush pixel parity. Open-file rename tests cover retaining
unsaved ink and saving only to the renamed source.

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

### Boox native handwriting and fallback

`BooxInk.java` uses Onyx `onyxsdk-pen:1.5.8` and
`TouchHelper.FEATURE_SF_TOUCH_RENDER` to request a direct display preview.
The official [pen SDK guide](https://github.com/onyx-intl/OnyxAndroidDemo/blob/master/doc/Onyx-Pen-SDK.md)
describes this separate handwriting path. `NotebookInput` owns the single
Android listener and attaches the optional bridge only on supported Boox devices.
Fineliner uses the vendor Pencil style, which the [official demo](https://github.com/onyx-intl/OnyxAndroidDemo/blob/master/app/OnyxPenDemo/src/main/java/com/onyx/android/eink/pen/demo/scribble/ui/ScribbleTouchHelperDemoActivity.java) renders as a
plain constant-width path. Its nine opaque `PEN_COLORS` use the canonical
canvas' displayed RGB as opaque ARGB, including grayscale preview. The Java
boundary independently restricts tool/color IDs and rejects translucent or
invalid ARGB. Final ink always uses Logistics' brush model.

The earlier Ballpoint Fountain preview was disabled after the physical test showed a thickness change
at pen-up. On the NoteAir5C, the SDK's Fountain companion raster renderer at a
nominal width of 40 produced widths 26/40/56/70/80 for pressures
0.1/0.25/0.5/0.75/1.0; Logistics' Ballpoint profile gives approximately
15.6/18.9/25.3/32.4/40.0. A single width multiplier cannot match the entire
pressure curve. This raster diagnostic does not measure the physical raw overlay.

The replacement `BooxBallpoint.java` uses the same plain native Pencil style
as Fineliner, with pressure-driven width updates. Raw position drawing remains
under the native driver's control. Raw move callbacks update `TouchHelper`'s
stroke width only when the canonical quarter-page-unit diameter changes,
using Ballpoint's existing pressure exponent and converting to screen pixels.
Each contact starts at the canonical minimum width; subsequent raw samples
update it. Original pressure samples still enter the existing canvas and save
queue; no vendor-computed widths replace stored ink. A failed width update leaves
the current contact's save handoff intact and selects ordinary input for future
Ballpoint contacts. The SDK's bitmap API is absent from this NoteAir5C firmware;
its separate direct-point API completed calls but produced no visible ink in
the physical test, so neither experimental path is used. Pressure-width updates
passed the synthetic callback/save/reopen checks and the subsequent physical
blue/red Ballpoint comparison. The tester confirmed live drawing and stable
thickness after lifting for both colors. Two blue contacts delivered 1,515
samples and two red contacts delivered 573; both pages saved and reopened with
identical widths and pressure within the format's 1/255 quantization. This is
subjective display acceptance, not an optical latency measurement.

Marker, textured pencils, Paintbrush, fixed-angle
calligraphy, Highlighter and Shader also retain fallback because their
pressure, texture, nib or blending behavior differs. Erasing and selection use
ordinary rendering and the existing DU refresh policy.

The bridge disables SDK-generated Android input. Native begin locks the current
canvas gesture; the completed point list then enters `logisticsNativePen` once
and follows the existing brush and ordered save queue. Pressure is normalized
using the device-reported maximum. Raw input pauses during reconciliation;
the raw preview retires after WebView's visual-state callback, then the current
configuration resumes. Notebook tools, pressure-derived widths and binary saving
remain under Logistics' control.

The local notebook WebView exposes only a bounded numeric preview configuration
interface, with no filesystem access. Mobile chrome publishes canvas/viewport
clipping, toolbar exclusions and brush/layer/page identity. Menus, read-only
state, warnings and non-stroke commands disable native preview. Changes to the
configuration cancel an outstanding native gesture; focus loss, detach and
close retire it. SDK initialization/configuration failures leave ordinary input
available. Android history samples are backed up during raw ownership; if a
completed contact produces no native begin callback, they replay once and the
native helper closes for that view. This guards firmware which reports an enabled
reader without delivering hardware samples.

Packaging excludes obsolete Android support dependencies, enables Jetifier and
selects one shared C++ runtime as in the vendor demo. The source manifest and
reused-project configuration both include the pen dependency and native bridge.

Run the physical comparison with the mobile interpreter:

```sh
PYTHONPATH=Python:. mobile_build/.venv/bin/python -m mobile_build.validation.document_storage_tools android \
  --probe boox-raw-ink --device DEVICE_SERIAL \
  --output test-results/boox-native-ink/physical
```

The comparison manager additionally includes the older standalone test-only
`BooxRawInk.java` bridge. Its baseline disables the production native preview.
The manager creates a disposable build with this test source. Its isolated package is `io.github.ispaure.logisticsrawinkqa`.
The on-screen instructions request two physical pressure-varying strokes with
the current renderer, then two with the native preview. The probe checks raw
callbacks, duplicate strokes, pressure and save/reopen precision. It saves
evidence before uninstalling the QA package, including on timeout; it preserves
the main app and its data. ADB-injected input cannot validate this hardware path.

On October 26, the NoteAir5C/Android 15 build loaded the SDK, discovered the Wacom
digitizer and reported a maximum pressure of 4095. The first comparison timed
out waiting for baseline strokes. A subsequent physical trial completed both
stages: the native path delivered 3,999 samples across two strokes, with pressure
up to 1.0, no rejected or duplicate strokes, and canonical widths of 1.5–4.0.
Both strokes saved and reopened with identical coordinates, pressure and widths.
The user reported that stage 2 was noticeably faster. This is a subjective
comparison using Ballpoint and an approximate vendor Fountain preview, not an
optical timing measurement or acceptance of the other brushes. Native-window
bitmap captures do not establish display latency or raw-overlay appearance.
The helper closed and the QA package was removed; only the main Logistics
package remained. A separate nine-brush codec fixture retained tool/color/width
data and pressure within the native format's 1/255 quantization; it does not
validate live native previews for all those tools.

The production integration's `notebook-input` device probe checks native enablement
for Fineliner and Ballpoint, fallback for the other seven brushes, menu clipping, all nine
palette colors in both normal/grayscale views and missing-callback
Android replay. It also injects three timed raw Ballpoint contacts (black, blue
and red) through the production callback and native width setter, comparing each
canonical width with the Java preview width and the reopened archive. This
checks the handoff and serialization, not physical digitizer latency. The earlier black-Ballpoint NoteAir5C run also passed pressure history,
no-duplicate ink, finger paging, page insertion and thumbnails. These checks do
not measure optical latency. Broader physical brush previews remain gated on
appearance comparisons; camera-based timing and continued real-pen lifecycle
checks remain useful acceptance work.

The earlier expanded NoteAir5C SDK matrix passed all 36 color/grayscale configurations,
both style selections, seven fallback brushes, menu clipping, missing-callback
replay and retained pressure history with no duplicate strokes. Main build
202610317 includes this extension and the separate mobile bitmap-memory fix.
The isolated QA package was removed and main restored with its data preserved.
These configuration checks do not measure physical hue accuracy or optical
pen-to-pixel latency.

The host `notebook_mobile_ui_probe.py` injects a configuration-only fake bridge
before page startup. It verifies 18 Fineliner and 18 Ballpoint color/grayscale configurations
and seven other brush fallbacks in a real browser, alongside its mobile
layout, pointer, pressure, page and recovery checks. This validates configuration
production and saved-model independence, not the physical screen's hue or nib
appearance; the Android companion probe exercises the actual SDK setters.

For a physical appearance/save check, run the same Android driver with
`--probe boox-preview --device DEVICE_SERIAL`. It opens a synthetic two-page
notebook: blue Ballpoint and red Ballpoint. Every page asks for
two curves, saves and reads back coordinates/pressure/widths, then replaces the
live model from the saved archive in the existing WebView. The test explicitly
adopts the observed recovery revision before further edits; the stale-writer
guard remains enabled. The tester inspects the reopened
ink and advances with Next / Finish. All pages are pre-created and their
transitions preflighted. The driver retains observations and the synthetic
archive before removing its isolated package; main-app documents are untouched.
Short strokes during native-frame reconciliation may use ordinary input, so
raw callback counts alone do not establish duplicate strokes.

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
It also checks square ink swatches inline at desktop width, narrow-window wrapping,
the desktop Pages Overview thumbnail response and selection, and insertion after
the current page. Desktop and mobile overviews share bounded `page_previews`
responses; previews do not change notebook bytes or page order.
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
claimed by the host tests. Briefs 02–04 remain open for physical hardware acceptance; the non-physical
checks below do not establish digitizer behavior or reMarkable firmware compatibility.

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


## Non-physical acceptance for briefs 02–04 — October 25, 2026

The remaining software acceptance passed on native macOS Qt, an Android 36
arm64 emulator and an iPad simulator using WKWebView (iOS simulator SDK 27.1).
Focused host regressions passed 47 desktop/model/resource cases and 50 mobile
cases. Existing unrelated checkout edits are not included in this acceptance.
Native build manifests retain the precise dirty-source fingerprint and shared
library identity; Android and iPad used the same source fingerprint.

`notebook_acceptance_probe.py` and the shared native test module
`notebook_acceptance_checks.py` generate 36-page notebooks with 433 strokes,
34,562 points, two layers, nine tools and three widths. Both legacy page lists
and modern `cPages` exports passed independent remarquee v0.0.14 page-identity,
page-order and stroke-count verification, including reorder/copy/delete and a
retained tombstone. The independent probe accepts repeatable `--archive` arguments
for archives generated in the actual Android/iOS runtimes as well as desktop.

Partial-write ENOSPC/EACCES injection, duplicate-name refusal, cancellation,
failed manifest publication and retry preserve the previous file and acknowledged
ink. Desktop additionally kills disposable writer processes after a checkpoint
and during manifest publication, then verifies recovery from a fresh repository.
The native mobile driver rotates portrait/landscape/portrait, backgrounds/resumes
its QA app, terminates it, relaunches it and explicitly reopens the recovered
notebook while comparing page identities and exact ink-frame hashes. Native
WebView export commands retain the draft after injected destination failures or
cancellation and can continue drawing. Destination failures are injected rather
than filling a device or changing its permissions.

Desktop Export Copy now uses the existing OperationProgress worker for encoding
and verified publication. Native timer delivery, cancellation before publication,
failed export, retry, source preservation, encrypted-source confirmation and
suffixed-name overwrite cancellation passed. Save/Save As, pending-ink ordering,
nine-brush bursts, erase/move/undo, large-page drawing, menus/zoom and brush raster
checks passed. The export worker does not retarget the source document.

With allocation tracing enabled, this 36-page encoding took about 2.20 seconds
on desktop, 1.09 seconds on Android and 2.68 seconds on iPad, with approximately
1.1 MiB peak traced Python allocations during encoding. This excludes the
pre-existing notebook model and native renderer memory. The mobile event loops
continued to run; maximum observed timer gaps were 0.234/0.360 seconds on
Android/iPad in these shared-host runs. These measurements establish neither
hardware latency nor a hitch-free frame budget for every notebook size.
All isolated QA apps and manager-owned simulator/emulator devices were removed.

Only physical acceptance remains for these briefs: real Boox pressure/palm and
pen-to-visible-pixel behavior, a physically drawn capture-to-export session,
and actual reMarkable import/select/move/erase/re-export on the recorded model
and firmware. Physical Apple Pencil behavior also remains unverified. Use the
[hardware procedure](hardware-acceptance.md); generated archives and independent
readback cannot satisfy those gates.

## Partial and whole-stroke erasing

The shared pointer engine defaults to partial erasing with Small/Medium/Large
radii of 8/16/32 page units. Pressing Erase opens a shared accessible settings
dialog on desktop and a nonmodal floating panel on mobile; type and size remain
local to that canvas. The mobile brush picker also floats below its toolbar
button. Outside pointer-down dismisses either panel without consuming the event;
the direct Android pen entry follows the same dismissal path. Tapping the opener
again closes its panel, and opening another panel replaces it.
`eraser.py` clips polylines against the swept circular path, including gaps
between delivered pointer samples. Cut boundaries interpolate pressure and
width; fragments retain brush, color, RGBA, thickness and layer. Hidden layers
are excluded. Whole-stroke mode uses the same swept hit geometry. Commands
checkpoint once per gesture and participate in ordinary undo/redo. The legacy
ID-based erase command remains available for existing callers.

Partial-eraser movement paints only the new segment batch into the page canvas;
it does not replay the whole page or the accumulated eraser path per movement.
The completed mask stays visible until the host acknowledges the edit, avoiding
old ink flashing back at pen-up. Cancellation and failed commands reconstruct
the durable scene. The shared input probe checks bounded preview batches, no
full-page clears during movement and mask persistence through pen-up.

For longer gestures, the commit algorithm indexes eraser sweep bounds in page
cells, then applies the unchanged exact capsule/variable-width intersection only
to nearby candidates. Long sweeps use a bounded fallback list; short gestures
keep the simpler full scan. Whole-stroke mode stops at its first confirmed hit.
`test_eraser_index.py` compares indexed and full-scan geometry for dense paths,
long sweeps, dots, hidden ink and both erase modes. A host fixture with roughly
14,000 ink segments and 499 eraser segments improved from 13.25 s to 0.15 s;
this is a software benchmark, not physical Boox display latency.

Native export places new fragments between their original scene neighbors,
preserving stacking order when an imported stroke is split. The model tests
cover sparse crossings, size differences, dots, hidden layers, repeated cuts,
round-trip order/style, recovery and failed-checkpoint rollback. The shared
brush WebEngine probe checks settings and pointer command fields in both
presentations. Physical stylus acceptance remains separate.


## Canvas memory bounds

The shared viewport reuses the page, draft and mask bitmaps when their backing
dimensions stay the same. Assigning canvas width/height, even to their existing
values, discards storage; ordinary page changes now redraw without reallocating
all three surfaces. A real resize resets their transforms and redraws stored ink.

The mobile composer supplies an 8-megapixel budget per bitmap. CSS dimensions
still follow zoom, but backing scale stops growing at that budget. This bounds
the three RGBA stores to approximately 96 MiB before compositor/driver copies;
it is not a limit on total app memory. Page coordinates, pressure and exported
geometry are unchanged. Desktop uses a 16-megapixel budget per bitmap
(approximately 192 MiB for the three RGBA stores, before compositor copies).
The budgets preserve normal full-page resolution; very high magnification can
soften the screen preview without changing saved native ink.

The isolated `notebook_memory_probe.py` exercises timed native Android pen events
on pages one and two at fit width and 200% zoom, repeated page switches, buffer
resize-write counts and exported ink readback. Use the owning document-storage
runner with `--probe notebook-memory --device SERIAL`; it saves incremental
memory evidence and removes its QA identity afterward. The unbounded renderer
reproduced foreground low-memory kills on NoteAir5C during the 200% zoom change.
Keep private document backups and raw device evidence under ignored test results.

The October 26 NoteAir5C fixed run completed 128 synthetic strokes across both
pages, including timed pen events at fit width and 200% zoom, with all 128
strokes present after export/readback. Same-size page switches made zero
backing-dimension writes; the largest bitmap was 2508 × 3344 pixels. Available
system memory stayed above 1.7 GiB in this run. This is a focused reproduction
and regression check, not a guarantee against all device-wide memory pressure.

The iOS `notebook_apple_memory_probe.py` and desktop
`Python/tests/notebooks/notebook_memory_probe.py` exercise all nine brushes and
three widths on pages one and two through fit, 100%, 150%, 200% and 400% zoom.
The shared checks compare native-decoded stroke dynamics, colors, widths, layers
and page order, require source files to stay unchanged until explicit Save, and
verify saved/exported readback. Native author UUIDs generated during encoding
are excluded from the ink comparison. Settled page pixels must match after a
zoom round trip on the same native rendering backend. The existing brush probe
separately checks live-preview geometry and brush raster behavior.

The October 26 cross-platform memory gate passed on native macOS Qt WebEngine
(109 synthetic strokes), an iPhone simulator (108), and an iPad simulator (108).
All three completed page-two writing and zoom through 400%, respected their
bitmap budgets, and retained source bytes until explicit Save. Native-decoded
saved ink matched, and settled pixels matched after fit/200% zoom round trips.
The separate all-brush live rendering probe and model/storage suites passed.
The iOS runs use real WKWebView with simulated pen events; this gate does not
certify physical Apple Pencil behavior. All
manager-owned iOS QA apps and simulators were removed.

The follow-up Fedora 43 aarch64 run passed the same page-two memory probe with
109 strokes, the 16-megapixel bound, zero same-size page reallocations, identical
settled zoom-round-trip pixels and exact native-decoded saved ink. The native
Qt 6.12 X11 backend ran under an owned Xvfb display with software graphics;
all-brush pixels, desktop drawing/history/saving stress and menus/zoom also passed.
This does not establish Linux GPU-driver or x86-64 parity. Ubuntu 24.04 model
regressions passed, but its native UI phase could not run without an existing
desktop display or Xvfb. Both Linux guest workspaces were removed after evidence
collection.

The Windows ARM64 guest with x64 Python/Qt 6.12 also passed the focused memory
probe (109 strokes), all-brush rendering and menus/zoom. Page-two mouse input,
16-megapixel backing bounds, unchanged source bytes before Save, exact saved ink
and zero zoom-round-trip raster differences all passed. This is emulated x64
coverage, not native x64 hardware acceptance. The broader normal-renderer stress
run exceeded its latency guard and its original 15-second large-file save wait;
those failures remain separate from the passing focused memory checks. The probe
now allows 60 seconds for save/export actions and drains pending publication
before teardown, preventing a failed test from destroying a writer or removing
its scratch files while they are in use. The drawing latency guard is unchanged.
The isolated retest with only these QA changes passed all 16 functional stress
checks, including saving a 1,007-stroke page after continued drawing, and removed
its guest workspace without a thread failure. Its normal-renderer frame gap
still reached 300.1 ms against the 80 ms guard, so Windows responsiveness remains
unresolved despite the passing memory, ink-quality and file-preservation checks.

## Dropdown presentation

The mobile WebView overflow uses commonUtils' `ui.native.web_dropdown` for
borderless command rows, menu semantics, initial focus and arrow/Home/End/Escape
navigation. The notebook host owns panel visibility, outside dismissal, focus
restoration and dispatch. The overflow and writing-tool popovers leave the
canvas visible and interactive, with no backdrop; an outside pointer dismisses
them without consuming the event. Mobile supplies touch sizing through CSS variables.
Logistics' E Ink stylesheet excludes menuitem buttons from its generic control
border rule, preserving flat command lists while outlining form controls.
Native mobile menus use `mobile.action_menu`; desktop menus use the shared Qt
menu host and theme. Keep native menus in those owners rather than replacing
them with WebView controls. `notebook_chrome_checks.py` checks computed borders,
focus, keyboard navigation and dismissal in normal and injected E Ink CSS through
the existing browser and native probe drivers.


### Android notebook view retirement

Retired Android notebook canvases first close native input/preview helpers,
detach the Toga widget, clear its content and explicitly destroy the ordinary
native WebView. Private WebViews already destroy their native view through
their existing privacy teardown. Blanking ordinary HTML alone retained native
renderer resources during repeated complete editor reopens; the physical QA
recorded an Android foreground LOW_MEMORY kill. Six subsequent remounts with
explicit destruction completed with app PSS around 346–351 MB. This retirement
check supplements the separate page/zoom bitmap-memory limits.
