# Notebook viewport and pen input

`assets/viewport.js` maps native page units to the display. Layouts with a Pro or Move template format fit the selected page on open and rotation. The template and ink share a 1404 × 1872 coordinate space. Move shows the centered 821 × 1460 region and expands that region for existing ink and images. If imported ink increases canvas height, the template still starts at the native origin. Portable template exports fit the embedded PDF box.

For other notebooks, narrow portrait frames the centered 821-unit strip, wide portrait fits the whole page and opened landscape Duo fits compact height. Other landscape layouts fit width. Format-2 `bestFit` and `fitToHeight` notebooks use the embedded PDF crop box at 226 dpi and retain the native horizontal center. `bestFit` opens framed to that box, including on iPhone Duo. Older PDF annotation copies use their legacy ink canvas.

Explicit zoom preserves scale and center through rotation/folds within scroll bounds. Default framing adapts. Fold changes wait for pen-up. Page changes and Reset restore fit while retaining an explicit Paper view for the open document. Reopening restores automatic framing.

## Touch navigation and palm rejection

`assets/input.js` routes one-finger horizontal navigation and two-finger pinch/pan. Select, Capture and explicit finger drawing keep editing gestures. Only the **+ Page** button confirms an end-of-book offer. Embedded Notes Library disables drawer swipes while notebook gestures own the surface.

Pen contact or proximity cancels unfinished touch input and blocks new touch gestures through a 250 ms post-release grace period. Toolbar controls remain active. Android uses hover MotionEvents and iPad can use a Pencil-only UIKit hover recognizer.

Native mobile WebViews collect every delivered pressure sample. The drawing canvas paints the initial contact, coalesces move previews at display frames, and flushes the remaining samples at pen-up before queuing the stroke for recovery.

On Android, the WebView listener groups move samples by frame and includes any remaining history with pen-up. The temporary mask and draft use software-backed contexts to reduce compositor work during blending.

## Native iOS Pencil transport

`LogisticsNotebookInputWindow` forwards system events once and sends transient packets only to the bound WKWebView. Normal release checks require compiled transport and matching canvas nonce at open and reload. DOM input is the usability fallback. Bounded serialized requests preserve coalesced order. Overflow, focus loss and retirement cancel submitted contacts and discard unsubmitted starts. Save and ordinary close flush native packets before waiting for JavaScript idle. UIKit force uses a constant fallback when unusable.

## Validation

From the configured checkout root, put Node on PATH and run:

Use a fresh run identifier for `RUN_ID`.

```sh
python3 dev.py test desktop --exact-file Python/tests/notebooks/test_touch_navigation.py
python3 dev.py test desktop --exact-file Python/tests/notebooks/test_native_pen_transport.py
PYTHONPATH=Python:. .venv/bin/python Python/tests/notebooks/notebook_viewport_probe.py --output tmp/test-results/RUN_ID/notebook-viewport
```

Expect independent swipe, link tap and pinch routes, valid FIFO/nonce handling and stable zoom through relayout. The physical rapid-tap loss report remains open. Use [hardware acceptance](hardware-acceptance.md) for pen delivery, palm, hinge and optical checks.

On a configured mobile build host, run the timed rapid-ink probe with the owning disposable targets.

```sh
PYTHONPATH=. mobile_build/.venv/bin/python -m mobile_build.validation.document_storage_tools android --probe notebook-rapid-ink --output tmp/test-results/RUN_ID/android
PYTHONPATH=. mobile_build/.venv/bin/python -m mobile_build.validation.document_storage_tools ios --family iPad --probe notebook-rapid-ink --output tmp/test-results/RUN_ID/ios
```

The probe replays short and long pressure strokes on three pages and checks ordered delivery, recovery, layer assignment, undo, redo, and Save/reopen. Android injects stylus MotionEvents into the real WebView listener. iOS replays the same sample sequence at the mounted canvas transport endpoint. The paint timing records a browser frame opportunity. Measure display refresh and physical pen delivery separately on the hardware.

Add `--android-gpu host` to use host graphics acceleration. For a comparison, keep the APK and emulator profile the same and verify the graphics adapter in each emulator log. The default renderer is SwiftShader.
