# Notebook brush calibration

## Try a brush change

In a disposable RMDOC, compare Medium Fineliner strokes before and after changing tool 17 in `brushes.py` from 3.5 to 3.75 page units. Update the Medium value in `test_constant_native_widths_and_highlighter_single_size` and `test_measured_thickness_scales_are_written_once`. Run the [focused regression](development.md#make-a-small-brush-change) and restore the measured width after the exercise. For raster changes see [Canvas rendering](#app-graphite-appearance).

`ink.py` and `assets/drawing.js` use the same catalog for saved and preview widths. Calculate dynamics once and round to the nearest quarter unit, minimum 0.25. Expanded PDF scenes use a derived catalog. Render imported widths directly, including zero. Thickness scale and pressure are already reflected in those point widths.

## Measured widths and colors

Measurements come from the November 4, 2026 Paper Pro worksheet, OS **3.29.0.153**, with twelve pages, 1,585 strokes and a native color PDF. All twelve pages opened without preservation warnings and retained unmodified scene bytes. Tests use synthetic geometry and aggregate values. For renewed measurement run `Python/tests/notebooks/measure_calibration.py` with `--archive`, `--pdf` and `--output` on a completed version-2 worksheet. Keep source files, hashes and reports under ignored test results.

| Tool | Thin / Medium / Thick point width |
| --- | --- |
| Fineliner | 2 / 3.5 / 5.25 constant |
| Mechanical Pencil | 3.5 / 5.25 / 7.75 constant |
| Highlighter | 26 Fixed |
| Ballpoint | 2.5 / 3.75 / 5.75 high pressure |
| Pencil | 2.75 / 5.25 / 8 upright |
| Marker | 5.5 / 6.25 / 9 nominal |
| Paintbrush | 4.5 / 8.5 / 12.75 upright |
| Calligraphy | 2.5 / 4.5 / 6.5 nominal nib spans |
| Shader | 10.75 / 19.5 / 28 plateau near 0.3 pressure |

Dynamics approximate measured profiles. Tilt, speed and native texture fidelity remain open. Thickness scales are approximately 0.8705015 / 1.7410030 / 2.6115046. Highlighter always uses the first scale and maps legacy size choices to Fixed.

PDF writing colors are blue `#304ae0`, red `#c23132`, green `#91da71`, yellow `#fae719`, cyan `#74d2e8` and magenta `#c07fd2`. Highlighter uses native IDs 3/4/5 for yellow/green/pink and 14/15/16 for blue/orange/gray. Preserve legacy color-9 RGBA and use preservation-only for unknown future colors. Shader uses color 9 and eight measured RGBA values. Supplementary sources include [Paper Pro field measurements](https://cable729.github.io/inkterop/docs/formats/remarkable/), [native RGBA examples](https://github.com/Scratchydisk/remarkable-rm#rgba-colour-discovery) and [Shader color definitions](https://github.com/ingatellent/xovi-qmd-extensions#changegreencolorqmd).

## App graphite appearance

`assets/drawing.js` anchors deterministic graphite grain to page units across live ink, saved ink and thumbnails. Pencil uses softer clustered gaps and Mechanical Pencil denser fine pits. Highlighter multiplies combined same-color coverage once per consecutive run.

## Canvas probe

From a configured desktop checkout on macOS/Linux:

```sh
PYTHONPATH=Python:. .venv/bin/python Python/tests/notebooks/brush_canvas_probe.py --output test-results/notebook-brushes/rendering
```

On Windows use `.venv\Scripts\python.exe` and `PYTHONPATH=Python;.`. Expect width parity and matching live/completed rasters. For headless failures retry with `QT_QPA_PLATFORM=offscreen` and `QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --disable-accelerated-2d-canvas"`. See [hardware acceptance](hardware-acceptance.md) for physical input.
