# Notebook viewport and pen input

`assets/viewport.js` maps native page units to the display. Narrow portrait fits the centered 821-unit Move strip, wide portrait fits the whole page and opened landscape Duo fits compact height. Other landscape layouts fit width. Format-2 `fitToHeight` notebooks use the embedded PDF crop box at 226 dpi and retain the native horizontal center.

Explicit zoom preserves scale and center through rotation/folds within scroll bounds. Default framing adapts. Fold changes wait for pen-up. Page changes and Reset restore fit while retaining an explicit Paper view for the open document. Reopening restores automatic framing.

## Touch navigation and palm rejection

`assets/input.js` routes one-finger horizontal navigation and two-finger pinch/pan. Select, Capture and explicit finger drawing keep editing gestures. Only the **+ Page** button confirms an end-of-book offer. Embedded Notes Library disables drawer swipes while notebook gestures own the surface.

Pen contact or proximity cancels unfinished touch input and blocks new touch gestures through a 250 ms post-release grace period. Toolbar controls remain active. Android uses hover MotionEvents and iPad can use a Pencil-only UIKit hover recognizer.

## Native iOS Pencil transport

`LogisticsNotebookInputWindow` forwards system events once and sends transient packets only to the bound WKWebView. Normal release checks require compiled transport and matching canvas nonce at open and reload. DOM input is the usability fallback. Bounded serialized requests preserve coalesced order. Overflow, focus loss and retirement cancel submitted contacts and discard unsubmitted starts. Save and ordinary close flush native packets before waiting for JavaScript idle. UIKit force uses a constant fallback when unusable.

## Validation

From the configured checkout root, put Node on PATH and run:

```sh
python3 dev.py test desktop --exact-file Python/tests/notebooks/test_touch_navigation.py
python3 dev.py test desktop --exact-file Python/tests/notebooks/test_native_pen_transport.py
PYTHONPATH=Python:. .venv/bin/python Python/tests/notebooks/notebook_viewport_probe.py --output test-results/notebook-viewport
```

Expect independent swipe, link tap and pinch routes, valid FIFO/nonce handling and stable zoom through relayout. The physical rapid-tap loss report remains open. Use [hardware acceptance](hardware-acceptance.md) for pen delivery, palm, hinge and optical checks.
