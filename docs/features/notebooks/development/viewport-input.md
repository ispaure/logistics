# Notebook viewport and pen input

The mobile canvas chooses a paper view from the available layout. These choices
change the displayed region and zoom, without changing the document's page size
or stored handwriting.

| Layout | Default view |
| --- | --- |
| Narrow phone or closed Duo in portrait | Fit the centered Paper Pro Move width |
| iPad or wide opened Duo in portrait | Show the whole Paper Pro page |
| Phone, tablet or opened/closed Duo in landscape | Fit the full Paper Pro page width |
| Duo laptop writing area | Fit the full page width across the writing area |

Native device identity distinguishes an iPad from a narrow phone window. Android
uses the current smallest screen-width configuration; portable browser previews
fall back to geometry. Portrait windows at least 700 CSS pixels wide use the
whole-page default. The canonical Move strip is 821 page units wide, centered
within the 1404-unit native page. Existing surrounding ink remains reachable by
panning and does not shrink that default strip to fit the entire drawing.

A deliberate zoom preserves the current page scale and center through rotation,
opening/closing and laptop transitions, subject to the document's scroll edges.
The unchanged default instead adapts to the new layout. Fold changes wait until
the live pen contact finishes. Every page change resets the zoom and position;
returning to an earlier page also starts at its current layout's default.
The visible mobile **Reset** zoom button applies that default immediately.
An explicit Paper view choice remains a manual override until reset or a page
change. Viewport state is presentation state and is not saved into native ink.

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
restoring ordinary Notes Library swipes after returning to Markdown. Native
browser gesture delivery still requires the coordinated acceptance slot.

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
