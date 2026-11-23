# Notebook brush calibration

## Try a brush change

Open a disposable RMDOC through the [desktop chooser](development.md#follow-a-stroke-from-drawing-to-save). Compare Medium Fineliner strokes before and after changing tool 17 in `brushes.py` from 3.5 to 3.75 page units. Update the Medium value in `test_constant_native_widths_and_highlighter_single_size` and `test_measured_thickness_scales_are_written_once`. Run the [focused regression](development.md#follow-a-stroke-from-drawing-to-save) and restore the measured width after the exercise. For raster changes see [Canvas rendering](#app-graphite-appearance).

`ink.py` and `assets/drawing.js` use the same catalog for saved and preview widths. Calculate dynamics once and round to the nearest quarter unit, minimum 0.25. Expanded PDF scenes use a derived catalog. Render imported widths directly, including zero. Keep the separate stored thickness field alongside the point widths. Rendering uses the widths directly.

## Measured widths and colors

Tests use synthetic geometry. The ranges below are in native page units.

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

Pencil broadens into side shading as a supported stylus slopes toward the page. The resulting width is saved in the native points. Upright and pressure-only input use the Pencil pressure curve. Shader uses pressure and composites overlapping color. Physical input testing and native texture fidelity remain open. Thickness scales are approximately 0.8705015 / 1.7410030 / 2.6115046. Highlighter always uses the first scale and maps legacy size choices to Fixed.

PDF writing colors are blue `#304ae0`, red `#c23132`, green `#91da71`, yellow `#fae719`, cyan `#74d2e8` and magenta `#c07fd2`. Highlighter uses native IDs 3/4/5 for yellow/green/pink and 14/15/16 for blue/orange/gray. Preserve legacy color-9 RGBA and use preservation-only for unknown future colors. Shader uses color 9 and eight measured RGBA values. Supplementary sources include [Paper Pro field measurements](https://cable729.github.io/inkterop/docs/formats/remarkable/), [native RGBA examples](https://github.com/Scratchydisk/remarkable-rm#rgba-colour-discovery) and [Shader color definitions](https://github.com/ingatellent/xovi-qmd-extensions#changegreencolorqmd).

## App graphite appearance

`assets/drawing.js` anchors deterministic graphite grain to page units across live ink, saved ink and thumbnails. Pencil uses soft variation with visible paper tooth. Mechanical Pencil uses a denser, continuous fine lead. Highlighter multiplies combined same-color coverage once per consecutive run.

## Canvas probe

From a configured desktop checkout on macOS/Linux:

Use a fresh run identifier for `RUN_ID`.

```sh
PYTHONPATH=Python:. .venv/bin/python Python/tests/notebooks/brush_canvas_probe.py --output tmp/test-results/RUN_ID/notebook-brushes/rendering
```

On Windows use `.venv\Scripts\python.exe` and `PYTHONPATH=Python;.`. Expect width parity and matching live/completed rasters. For headless failures retry with `QT_QPA_PLATFORM=offscreen` and `QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --disable-accelerated-2d-canvas"`. See [hardware acceptance](hardware-acceptance.md) for physical input.
