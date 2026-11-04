# Native stroke lasso selection

The shared desktop/mobile editor uses `assets/selection.js` for Select mode.
Finger, pen and mouse draw a dashed polygon; finger selection does not require
finger drawing to be enabled. Existing pen proximity and palm rejection still
apply. Only strokes on visible layers whose complete segments and painted
diameters fit inside the polygon are selected. Testing endpoints alone is
insufficient for concave polygons.

The selection has one dashed bounding box, four square uniform-scale handles and
a circular rotation handle above its top edge. Dragging inside moves it. Rotation
integrates wrapped angular deltas, so a given tangential movement is finer farther
from the centre. Pointer capture allows transforms to continue beyond the paper;
the backend rejects final geometry outside the page. Cancellation restores the
original preview without issuing an edit. Lasso paths exceeding the bounded
gesture buffer are rejected rather than selecting from a truncated polygon.
Containment prepares one exact edge AABB index per lasso and caches interior-cell
certificates. A cell is accepted only when no polygon boundary crosses it;
this does not rasterize or approximate the selection. A shared work budget aborts
the whole selection on pathological input, clearing any partly accumulated IDs.
Visible-ID reconciliation uses sets rather than a nested scan of all strokes.

`input.js` routes native pen-up and pinch/palm cancellation through
`selectionFinish`; wrapping DOM pointer-up alone would miss those paths.
`viewport.js` draws the overlay after the scene. The PDF link wrapper delegates
Select gestures to the selection handler. Capture retains its separate image
clipboard and owns its keyboard routing.

## Durable commands and clipboard

`Editor` implements `copy-strokes`, `cut-strokes`, `paste-strokes` and extends
`transform` with a uniform scalar, angle in radians and page-space pivot.
Protocol validation rejects nonfinite numbers and unsupported scales. Selection
commands validate visible stroke IDs. Mutating operations use existing
checkpoint rollback and Undo/Redo. Copy has no checkpoint or undo entry.

The private stroke clipboard survives page changes and undo until the editor
closes. It stores page-space geometry, independently of display zoom and scroll;
both copied and cut strokes paste at their original page positions. Paste assigns
fresh IDs and the active visible layer, enforcing page and point limits. The
acknowledged `selection_ids` use IDs after recovery normalizes the native scene.

Transforms preserve pressure and update diameter uniformly. For existing native
lines with unchanged point counts, serialization retains speed and direction,
updates changed point values and writes the transformed thickness-scale metadata.
An identity transform keeps the original scene bytes. Unrelated imported strokes
remain untouched. See [saved stroke sampling](stroke-sampling.md) for the separate
new-stroke reduction policy.

## Verification scope

`test_stroke_selection.py` covers actual editor/codec/recovery operations,
cross-page Copy/Cut/Paste, fresh IDs, native metadata, Undo/Redo, failed checkpoint
rollback and invalid transforms. `selection_work_logic.js` invokes the production
selection, input and link handlers in V8, including concave containment, painted
width, all pointer types, off-page precision, cancellation and native pen routing.
The combined Capture/Select keyboard check invokes both production clipboard
handlers together, including the Capture-only routing guard and modal blocking.
`selection_index_logic.js` compares the index to an exhaustive geometry oracle:
16,508 deterministic checks cover concave and self-crossing contours, boundary
epsilon, painted radius, stationary samples and degenerate outlines. An operation
count fixture processes one million dense interior samples against 2,048 edges
with 1,000,040 counted work units and one exact edge test. These are complexity
checks, rather than measured device latency.

On November 4, 2026, `selection_canvas_probe.py` passed on macOS Qt WebEngine
against Logistics `cce65617`, commonUtils `888872d1` and build SDK `0f9285bb`.
The desktop (1,200 pixels), phone (390 pixels) and tablet/iOS-style frame-batched
presentation (760 pixels) passed synthetic DOM finger/pen/mouse gestures,
full-stroke containment, uniform scale, rotation, cancellation, actual Python
Editor acknowledgements, original-position Copy/Cut/Paste and native save/reopen.
A corner tap on a half-unit dot emitted no edit. Tiny-dot and clipboard routing
also have failing-control V8 regressions.

All six compositor-fenced light/dark screenshots were inspected. Selection
outlines, square corners, rotation circles and Copy/Cut/Delete were visible;
Paste remained clear of the zoom dock, desktop footer and selection actions.
Geometry guards check that clearance and menu stacking in every presentation.
The complete controller finished in 20.59 seconds, with no claim of exclusive
benchmark conditions. Its private source, full SDK/submodule, Qt environment,
profiles, storage/cache and manager scratch workspace were removed, and its
owned process group had no remaining processes.

These are Qt WebEngine presentation checks, including mobile HTML, rather than
native Android WebView or iOS WKWebView acceptance. Synthetic events use a
capture-identity stub; physical pointer capture, pen latency, native mobile
touch behavior and reMarkable interoperability remain separate hardware gates.
