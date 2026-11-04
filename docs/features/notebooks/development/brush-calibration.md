# Paper Pro brush calibration

## November 4, 2026 sample

A completed twelve-page worksheet from a Paper Pro running OS **3.29.0.153**
contains 1,585 native strokes, including handwritten notes and calibration marks.
The matching native color PDF supplies a rendering reference. Original files,
handwriting coordinates, rendered pages and detailed measurements remain under
ignored local test evidence, outside the wiki and release payloads. Tests use
independently constructed synthetic geometry and aggregate numeric fields.

The supplied PDF-backed worksheet imported successfully, accepted native writing
and exported as both `.rmdoc` and color PDF. That establishes this particular
import/write/export path, not native selection/movement/erasure of generated ink,
other firmware, optical latency or Boox input behavior.

## Corrections shared by desktop and mobile

Native point widths are in scene units and already include tablet dynamics.
They must not be multiplied by thickness scale or pressure again. New strokes
use the following measured constant widths or approximate pressure profiles:

| Tool | Thin / Medium / Thick point-width reference | Scope |
| --- | --- | --- |
| Fineliner | 2 / 3.5 / 5.25 | Constant throughout the sample |
| Mechanical Pencil | 3.5 / 5.25 / 7.75 | Constant throughout the sample |
| Highlighter | 26, one Fixed size | The cover note and native fields agree; other worksheet bands contain explanatory pen writing |
| Ballpoint | 2.5 / 3.75 / 5.75 at high pressure | Fitted pressure response; not the firmware algorithm |
| Pencil | 2.75 / 5.25 / 8 upright reference | Low-tilt shading can be much wider and is not synthesized |
| Marker | 5.5 / 6.25 / 9 nominal reference | Width also varies with motion/pose; approximate |
| Paintbrush | 4.5 / 8.5 / 12.75 upright reference | Piecewise pressure response; speed/tilt remain approximate |
| Calligraphy | 2.5 / 4.5 / 6.5 nominal nib spans | Directional nib reconstruction remains approximate |
| Shader | 10.75 / 19.5 / 28 plateau | Pressure ramp saturates around 0.3; low-pressure widths 3.5 / 6.5 / 9.25 |

Native thickness-scale fields are approximately 0.8705015, 1.7410030 and
2.6115046. Highlighter always uses the first scale. These fields are written
alongside, rather than applied to, the already computed point widths. Older
three-width Highlighter commands remain accepted as aliases for the Fixed size;
the desktop and mobile controls expose only the single size.

Solid writing colors measured in the native PDF are blue `#304ae0`, red
`#c23132`, green `#91da71`, yellow `#fae719`, cyan `#74d2e8` and magenta
`#c07fd2`. Black, gray and white remain unchanged. Highlighter uses native IDs
3/4/5 for yellow/green/pink and **14/15/16 for blue/orange/gray**. The latter IDs
are explicit additions to the vendored codec; arbitrary unknown future colors
still cause preservation-only handling. The Highlighter palette is tool-specific,
so legacy writing color IDs are not reinterpreted globally. Previously imported
color-9 RGBA highlights remain intact. Shader retains native color 9 and its
existing eight measured RGBA values, which this worksheet confirms.

`brushes.py` supplies the shared catalog. Python creation and browser preview
interpolate the same pressure knots and quantize once to quarter-units. The Boox
Ballpoint preview receives the shared factor/exponent through its configuration
and accepts the measured base widths. This changes only its math/configuration;
it does not constitute a new physical pen test.

## Validation and remaining limits

The original archive now opens all twelve pages without preservation warnings;
unchanged ink roundtrips retain the original scene bytes. Before the color-ID
fix, the complete last page became preservation-only because the codec rejected
14–16. The raw input files remain unchanged.

On this same calibration sample, mean absolute point-width error changed as
follows. These are calibration-set comparisons, not held-out firmware tests or
pixel/texture similarity scores. Tilt and speed tasks are included:

| Tool | Previous mean error | Updated mean error |
| --- | ---: | ---: |
| Fineliner | 1.241 | 0 |
| Mechanical Pencil | 3.961 | 0 |
| Highlighter | 11.000 | 0 |
| Ballpoint | 1.434 | 0.061 |
| Pencil | 2.232 | 0.924 |
| Marker | 2.139 | 1.413 |
| Paintbrush | 2.142 | 0.628 |
| Calligraphy | 2.360 | 1.249 |
| Shader | 9.159 | 0.023 |

Focused pure model/calibration regressions and the serial Qt WebEngine brush
probe cover desktop, mobile and iOS-scheduled HTML: per-tool width controls,
native IDs/palettes, Python/JavaScript parity, native-width preservation,
grayscale isolation, Shader compositing and preview/completed raster agreement.
The optional `boox_ballpoint_parity.py --output ...` checks all 256 pressure
levels at three widths (768 cases) with portable Java and a TouchHelper stub.
It does not build Android or exercise the real SDK.

Focused Android package acceptance also passes against the production compiled
`BooxBallpoint`: all 768 cases through both the default and explicitly configured
curve (1,536 Android method invocations). The packaged `TouchHelper` class links
in Android. Four synthetic stylus MotionEvent gestures pass through production
`NotebookInput`: three Ballpoint sizes/colors and blue Highlighter, each saving
exactly one six-point stroke. Pressure, quarter-unit widths, native color/scale
and archive roundtrips agree; Highlighter stays at 26 units with one UI size.
The test fits the full page and verifies the visible canvas/native-view bounds
before drawing. Reusing the source-verified QA package changes only its Python
payload; DEX and native libraries are checked byte-for-byte after restaging.
The QA app, disposable emulator and scratch workspace are removed afterward.
This narrow check does not cover the complete native input/history suite, actual
Onyx driver attachment, physical stylus behavior or optical latency.

`measure_calibration.py --archive ... --pdf ... --output ...` reads a completed
version-2 worksheet and emits counts, ranges, native colors and source hashes.
Keep its output under ignored test results. It refuses unsupported pages rather
than reporting partial measurements as complete.

Exact textured rendering, speed/tilt response, native calligraphy nib behavior,
other tablets/firmware and physical pen-to-pixel behavior remain unverified.
No repeat of the supplied worksheet is needed to use these measurements. The
remaining interoperability procedure is [hardware acceptance](hardware-acceptance.md).

## App graphite appearance

Pencil and Mechanical Pencil use original procedural graphite materials in
`assets/drawing.js`. The Pencil material combines fine tooth with clustered
paper gaps and a softer body. Mechanical Pencil keeps a denser lead with sparse
fine pits. A deterministic, seamless paper field replaces the former repeating
eight-unit lattice. Texture coordinates stay anchored to native page units and
are shared by completed strokes and incremental draft recoloring.

This is editor presentation. Native point arrays, pressure/width calibration,
scene thickness scales, brush IDs and portable exports retain the same values.
Export converts templates to vector PDF backgrounds independently of the Canvas
renderer. Stored handwriting remains editable native geometry; the bounded
Canvas backing is its on-screen compositor.

Two 128-by-128 alpha masks are reused across colors, and a 24-entry material
cache bounds colored tiles. Selected styles are prepared on tool, color and
grayscale changes before the next pen contact. Active-contact events do not
trigger this prewarming. Live drawing continues to update only the new segment's
mask bounds; pen-up composites the accumulated ink bounds without replaying the
stroke. The existing Boox Ballpoint/Fineliner direct-preview eligibility and
complete-stroke handoff are unchanged. Pencil tools keep the shared incremental
Canvas path; this change does not add a vendor SDK brush mode.

The original synthetic graphite fixture checks visual distinction, stable
redraws, history-density independence, zoom, hue/grayscale, live/committed
agreement and native/export member invariance. Its timings describe the tested
browser, rather than physical Boox pen latency. No tablet textures, proprietary
brush code or private handwriting are included in the implementation or tests.

On November 4, 2026, private Qt 6.12 browser checks passed for desktop, mobile
and the iOS scheduling presentation, followed by the existing nine-brush
regression checks. The tested source and fixture hashes were captured. Native
scene and portable-export members stayed byte-identical with identical export
clock inputs. UI prewarming left the first preview with no new texture allocation
or upload; a move after 2,000 points processed only its two-point tail. Pen-up
replayed no geometry and retained identical pixels. The private environment,
source/SDK snapshots and caches were removed afterward. This does not establish
physical tablet responsiveness or reproduce firmware texture algorithms.
