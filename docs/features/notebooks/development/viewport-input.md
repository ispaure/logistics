# Notebook viewport and pen input

The mobile canvas chooses a paper view from the available layout. These choices
change the displayed region and zoom, without changing the document's page size
or stored handwriting.

| Layout | Default view |
| --- | --- |
| Narrow phone or closed Duo in portrait | Fit the centered Paper Pro Move width |
| iPad or wide opened Duo in portrait | Fit the whole page |
| Opened Duo in landscape | Fit the compact reference height and start at the top of larger pages |
| Other phones or tablets in landscape | Fit the notebook page or rendered PDF to the available width |
| Duo laptop writing area | Fit the full page width across the writing area |

Native device identity distinguishes an iPad from a narrow phone window. Android
uses the current smallest screen-width configuration; portable browser previews
fall back to geometry. The whole-page default starts at 650 CSS pixels on Duo to
include its 669-point inner portrait screen, and at 700 CSS pixels on other
phones. Landscape Duo windows at least 560 CSS pixels tall use the compact
height default. The canonical Move strip is 821 page units wide, centered
within the 1404-unit native page. Existing surrounding ink remains reachable by
panning and does not shrink that default strip to fit the entire drawing.
Where landscape uses width fitting, PDF fitting measures the rendered background.
The mobile zoom readout is relative to the current page’s height fit. At 1.0×,
the page spans the usable height.

Native format-2 PDF notebooks with `fitToHeight` use their embedded PDF crop
box in 226-dpi ink units, matching the coordinate space used for native ink.
The canvas expands when the background exceeds the legacy 1404 × 1872 frame.
The bridge translates horizontal coordinates for display and edits around the
original native center. The compact opening dimensions use the same coordinate
space. New strokes use the expanded brush profile in both the canvas preview and
the saved stroke. PDF link rectangles are mapped to the painted raster, including
any margins around it.

A deliberate zoom preserves the current page scale and center through rotation,
opening/closing and laptop transitions, subject to the document's scroll edges.
The unchanged default instead adapts to the new layout. Fold changes wait until
the live pen contact finishes. Every page change resets the zoom and position;
without an explicit Paper view choice, returning to an earlier page starts at
its current layout's default.
The visible mobile **Reset** zoom button applies that default immediately.
An explicit Paper view choice applies across the open document. Page changes and
Reset zoom reset scale and position while retaining that view; reopening restores
automatic framing. An explicit Paper view takes precedence over the template’s format. Viewport
state is presentation state and is not saved into native ink. The template format
selector is shown only for `FORM_TEMPLATES`, whose Pro and Move layouts differ.

## Touch navigation

The shared canvas reserves ordinary single-finger horizontal drags for page
navigation at any zoom, including touches beginning in the viewport margins or
over PDF links. Vertical drags do not pan. The existing two-contact focal-point
zoom also provides horizontal and vertical panning; a remaining finger stays
inert until all contacts lift. Explicit finger drawing, Select / move and Capture
retain their editing gestures. Pen proximity/contact rejection still takes priority.

A left swipe beyond the last page offers a right-side **+ Page** button. Only its
explicit click sends `add-page`; read-only and locked documents cannot offer it.
The offer expires on navigation and successful creation, and permits retry after
an acknowledged failure. Notes Library's embedded notebook marks ownership of
horizontal document swipes, disabling native drawer-opening recognizers and the
central `open_swipe` entry point while retaining the pane buttons.

The reusable `touch_navigation_logic.js` executes production palm, input, zoom,
link and navigation handlers together. It checks page boundaries, zoomed/margin
swipes, link taps, cancellation, two-finger pan/pinch and page-creation acknowledgment.
Mobile dummy-backend tests cover notebook drawer exclusion, button access and
restoring ordinary Notes Library swipes after returning to Markdown.

On November 4, 2026, the actual Cocoa Qt WebEngine check passed on Logistics
`71629c9e`, build-manager `ffbc831c` and commonUtils `64f93308`: nine desktop and
22 mobile assertions, including the document capture listeners at 200% zoom,
viewport-margin paging, stationary PDF links, no one-finger panning, two-finger
panning in both axes and the measured right-side page-creation button with an
explicit click and acknowledgment. Both layouts also passed the real three-second
Undo expiry. Rendered compositor screenshots were inspected; owned process groups,
source scratch and private SDK bootstrap were removed. The browser check dispatches
DOM PointerEvents; it does not certify OS finger delivery, native Notes Library
pane buttons or physical stylus behavior. Those native boundaries remain separate
from the passing browser and dummy-backend contracts.

## Palm rejection

The shared canvas rejects touch drawing, panning and pinching during a pen
contact or detected pen proximity over the paper, and for 250 milliseconds after
release. A pen taking over cancels an unfinished finger gesture without saving
its preview. The guard leaves toolbar controls available and restores ordinary
finger input after the bounded grace period. Focus loss and hidden-document
cleanup clear stale contact/proximity state.

Android observes stylus/eraser hover MotionEvents alongside its existing native
pen-history delivery. OS cancellation and canceled-up handling continue to
discard canceled strokes. On iPad, an optional Pencil-only UIKit hover recognizer
observes proximity without canceling WebView touches or taking over its normal
recognizers. Browser pen contact/cancel events remain the fallback. Hover depends
on the actual tablet, pen and OS; iPhone is not treated as a Pencil device.

The platform contracts are described in Android's
[advanced stylus features](https://developer.android.com/develop/ui/views/touch-and-input/stylus-input/advanced-stylus-features)
and Apple's
[Pencil hover guidance](https://developer.apple.com/documentation/UIKit/adopting-hover-support-for-apple-pencil).
Application guards complement these signals; they cannot manufacture proximity
on hardware that does not report it.

## Validation boundary

The reusable `notebook_viewport_probe.py` exercises measured browser geometry,
fold transitions, zoom/focal-point preservation, reset controls and page changes.
On November 4, 2026, its real Qt WebEngine run passed eight phone/tablet/Duo
layouts, including laptop width fitting and hinge clearance. It also passed
surrounding-ink and PDF framing, manual Move selection, manual zoom through
rotation/folding, page-away/back resets and synthetic palm/contact/grace checks.
The browser result is bound to a captured source inventory. Layout checks wait
for the actual viewport size and completed resize acknowledgment, rather than
assuming a fixed number of frames. Each reloaded test canvas gets a fresh bridge
identity and command sequence, matching the native canvas lifetime.

Native adapter mock checks cover capability selection and observer retirement;
shared V8 checks cover proximity/contact/grace state. The changed Android hover
listener still needs compilation and native event acceptance, and the UIKit
observer needs a simulator installation/lifecycle check.
These checks do not certify physical hinge reporting, OS palm classification,
Pencil hover range, optical latency or stylus behavior on an actual tablet.
Current test results must be bound to the source and packaged native input code;
an older Android QA package does not validate a changed `NotebookInput` class.

## Native iOS Pencil transport

The project-owned `LogisticsNotebookInputWindow` captures Pencil contacts in its own
`UIWindow` event handler before forwarding through normal window dispatch,
independently of browser PointerEvents. Every system event is forwarded exactly
once. It leaves native controls, fingers and normal system gestures in charge.
Only an explicitly bound notebook WKWebView receives transient ink packets.
The named Toga factory returns an actual pinned `MainWindow` backend; existing
navigation containers and the scene backend's overrides remain unchanged.
Missing native support or an unsupported Toga constructor keeps ordinary DOM
input. A compiled binding is established before initial HTML publication, using
a fresh canvas nonce; queued packets cannot target a replacement document.
The normal iOS notebook release check requires the compiled window, enabled
binding and matching canvas nonce on initial open and reload. DOM fallback
preserves usability but does not satisfy that release check.

Native WK requests are serialized and bounded. Coalesced points retain order;
retirement, focus loss and overflow discard unsubmitted starts and cancel only
the contact already submitted. One native completion timer belongs to each
binding. Fixed native counters expose capture, dispatch, completion, timeouts
and queue depth without contact coordinates, document identity or Python work
per contact. A bounded three-second private diagnostic receipt refreshes observer,
canvas and window lifetime identities, while permitting only one outstanding DOM
query. Window-aggregate native counters and current-canvas DOM counters retain
explicitly different scopes; they are not advertised as one-to-one contact totals.
A hung DOM query does not cancel its native future or stop native counter refresh.
Compiled input does not install the older Python contact observer.

Pressure defaults to finite positive UIKit force divided by maximum force;
zero or unsupported values use visible constant pressure. This is event-payload
handling, not Pencil model detection. View and input offers an explicit
constant-pressure choice for the open canvas, including known USB-C Pencils.
Save retries acknowledge without clearing queued strokes. Normal Close and
embedded save flush native transport before checking JavaScript idle; an
explicit discard may intentionally retire unsubmitted input.

The native synthetic transport fixture covers twenty rapid one-point contacts,
FIFO delivery, force/coalescing, admission, cancellation, overflow and stale
nonces. It does not establish physical digitizer delivery or prove that the
reported physical rapid-tap loss has been resolved. A full app probe separately
checks Toga construction, model/checkpoint delivery and close/reopen behavior.
