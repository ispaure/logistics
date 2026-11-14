# Notebook brush calibration

Change the shared brush catalog for new ink on desktop, Android and iOS.
To change how that ink looks on screen, start with [Canvas rendering](#app-graphite-appearance).

## Try a brush change

Use a disposable RMDOC. In the desktop **New / Open Document** chooser, select
**Notebook (.rmdoc)**, choose **New**, create a blank page and save it to a
temporary folder. Reopen that file with **Open** in the same chooser. Select
Fineliner and Medium, draw a short stroke, then save and reopen to compare the
stored result with the live preview.

For example, try raising the Medium Fineliner width from 3.5 to 3.75 page units.
Edit tool 17 in `Python/features/notebooks/brushes.py` (`BRUSHES`), and update the
Medium expectation in both the constant-width and thickness round-trip tests.
Draw a fresh stroke after relaunch. A previously saved stroke retains its
original width. This is a disposable experiment. Keep the measured value in
production unless you have a new calibration.

Run this from the repository root with the desktop environment set up:

```sh
python3 dev.py test desktop --exact-file Python/tests/notebooks/test_brush_calibration.py
```

Expect six passing tests. They check constant widths, Shader saturation,
thickness fields, Highlighter IDs and round trips, legacy RGBA and unknown
colors, and writing colors. For preview or compositing changes, also run the
[Canvas probe](#canvas-probe). Use [hardware acceptance](hardware-acceptance.md)
for physical pen and firmware checks.

## How widths reach the file

`ink.py` calls `brushes.stroke_points` when adding new ink.
`editor.py` publishes the same catalog to `assets/drawing.js`, where
`pressureWidth` and `strokePoint` compute the live preview. Both use the
profile's power curve or interpolate its pressure knots, apply directional nib
scaling where configured, and round once to the nearest quarter page unit with
a minimum of 0.25. Expanded PDF scenes use a separate derived catalog with a
Fineliner override. On Boox, the native Ballpoint preview receives the factor,
exponent and base widths through its configuration.

Imported native v6 point widths already encode tablet dynamics in page units.
Render them directly, including zero widths. The separate thickness field is
stored alongside those widths. Applying that field or pressure again changes
imported ink.

## Measured widths and colors

The source is a twelve-page Paper Pro worksheet from November 4, 2026
(OS **3.29.0.153**, 1,585 native strokes) and its native color PDF. The
worksheet exercised PDF-backed import, writing and export as RMDOC and color
PDF on the sampled path. Tests use independently generated geometry and
aggregate numeric fields. For a new measurement, use the notebook test
utility `measure_calibration.py` with `--archive`, `--pdf` and `--output`.
It requires a completed version-2 worksheet and rejects unsupported pages.
Keep original files, hashes, coordinates and render reports under ignored
test results.

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

The constant widths and Shader saturation are directly observed. Ballpoint,
Pencil, Marker, Paintbrush and Calligraphy use fitted or approximate dynamics.
On the worksheet, the fitted mean absolute point-width errors in page units
were 0.061 for Ballpoint, 0.924 for Pencil, 1.413 for Marker, 0.628 for
Paintbrush, 1.249 for Calligraphy and 0.023 for Shader. The sample includes
tilt and speed tasks. All twelve pages open without preservation warnings and
unmodified ink retains the original scene bytes. Exact texture, speed and
tilt behavior and interoperability on other firmware still require validation.

The [manufacturer's writing tools guide](https://support.remarkable.com/s/article/Writing-tools)
and [OS 3.15 notes](https://remarkable.com/blog/remarkable-os-3-15-whats-new)
describe the tools and palette. Supplementary measurements and color definitions
come from [Paper Pro field measurements](https://cable729.github.io/inkterop/docs/formats/remarkable/),
[native RGBA examples](https://github.com/Scratchydisk/remarkable-rm#rgba-colour-discovery)
and the [Shader color definitions](https://github.com/ingatellent/xovi-qmd-extensions#changegreencolorqmd).

## App graphite appearance

Edit `Python/features/notebooks/assets/drawing.js` for on-screen brush
appearance. Pencil uses clustered paper gaps and a softer body. Mechanical
Pencil uses denser lead with sparse fine pits. The deterministic texture field
is anchored to page units, so live and completed strokes share the same grain.
Two reusable 128 × 128 alpha masks and a 24-entry material cache bound texture
work. Tool, color and grayscale changes prepare materials before contact.
Motion updates the latest segment's bounds and pen-up composites the existing
mask. Native point data and portable exports retain their own representation.

Highlighter accumulates opaque coverage for consecutive same-color strokes,
then multiplies the tint into the page once. This keeps crossings uniform
while underlying marks and template rules show through. Across an intervening
mark, the latest pass of a color owns the overlap. Pages Overview uses the same
renderer at thumbnail size.

## Canvas probe

Run from the repository root on macOS or Linux with the desktop environment
installed. On Windows use `.venv\Scripts\python.exe` and set `PYTHONPATH`
to `Python;.` in the shell before running the script.

```sh
PYTHONPATH=Python:. .venv/bin/python Python/tests/notebooks/brush_canvas_probe.py --output test-results/notebook-brushes/rendering
```

Expect matching Python and JavaScript widths, direct imported widths,
distinct brushes, grayscale isolation and matching live/completed raster
output in desktop and both mobile scheduling presentations. Inspect the
contact sheets and probe results in the output folder. This exercises real
Qt WebEngine with synthetic input. For native Boox math, the notebook test
utility `boox_ballpoint_parity.py --output ...` covers 256 pressure levels
at each of three widths with portable Java and a TouchHelper stub. Managed
Android package checks additionally exercise the compiled curve, SDK class
linkage and six-point synthetic Ballpoint and Highlighter gestures through
`NotebookInput`. Physical SDK attachment, stylus behavior and pen-to-pixel
latency remain hardware checks.
