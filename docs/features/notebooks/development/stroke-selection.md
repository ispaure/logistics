# Native stroke lasso selection

`assets/selection.js` selects visible strokes whose full painted segments fit inside the polygon. Its edge index and bounded work reject oversized or pathological gestures without partial selection. Finger, pen and mouse work in Select mode. `input.js` routes native pen-up, palm and pinch cancellation. Cancellation restores the preview. Capture has its own image clipboard.

`Editor` validates visible IDs and finite transforms. Mutations use checkpoint rollback and Undo/Redo. The editor's stroke clipboard keeps page-space positions across pages. Paste assigns fresh IDs on the active visible layer. Native transforms preserve pressure, speed and direction at unchanged point counts, updating widths and thickness. Identity transforms preserve scene bytes.

From the configured desktop checkout root:

```sh
python3 dev.py test desktop --exact-file Python/tests/notebooks/test_stroke_selection.py
PYTHONPATH=Python:. .venv/bin/python Python/tests/notebooks/selection_canvas_probe.py --output test-results/notebook-selection
```

Expect persistent transforms and clipboard geometry, undo/redo and checkpoint rollback. The Qt probe uses synthetic mouse, finger and pen. For physical input see [hardware acceptance](hardware-acceptance.md).
