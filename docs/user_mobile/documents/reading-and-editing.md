# Reading and editing on mobile

## Reader and editor presentation (Phase 3 Part 1)

Open EPUB and comic sessions now give content the main area, with compact page
navigation and a format-specific Actions menu. EPUB offers contents, bookmarks,
text appearance, chapter search and read-aloud; comics offer page navigation,
page layout, fit and neighboring-comic actions where supported. EPUB reading
mode hides those controls and keeps a visible Restore controls
button. Comics open with controls hidden and zero page margins; tap the page to
show or hide reading controls. Native navigation bars hide with comic controls
and return when controls are shown or when leaving the reader. EPUB appearance offers supported font sizes, margins and system/light/dark
colors without changing the current chapter. Progress remains chapter/page based.
Fit comic pages remain centered after leaving and reopening a reader or repeatedly
showing and hiding controls; zoomed pages retain bounded pan and zoom behavior.
Fullscreen reclaims the navigation area on both platforms, including Android's
title bar. Transfer banners appear with reading controls and stay hidden during
immersive comic reading; this does not pause transfers in the background.

In fullscreen comics on iOS and Android, hold a thumb on the page for about
400 ms to show a 2× magnifying bubble. The bubble enlarges the page beneath
its center and grows larger on tablet screens. The bubble sits close
to the thumb with a slight overlap. Keep holding and drag to move
the bubble. Near a screen edge, keep dragging toward the edge to inspect the
outermost pixels even after the bubble stops moving. Release to dismiss. The page stays still while the bubble is open. A second
finger cancels the bubble so pinch zoom remains available. The bubble is disabled
when reading controls are visible and is cleared on page changes or leaving the
reader. It works on single pages and spreads, including Local/LocalCrypt comics.

Comic pages use native pinch zoom and panning on iOS and Android. Fit page resets
zoom; swipe left for the next page and right for the previous page at fit size.
Manga reverses those directions. Swipes stop at the first/last page without an
error. While zoomed, dragging pans the page and does not change pages. Swipes
leave the outer edge available for system navigation. Private comic pages
use the same presentation while their content and position remain session-only.

Text actions offer Preview beside editor in wide windows. The preview stays beside
the editor at widths of at least 1100 points and collapses in narrower windows;
the preference belongs to that document session. Compact Edit/Preview remains
available. Both previews retain the existing offline renderer restrictions.

Simulator/emulator checks exercise zoom, fit, page direction, reading-mode restore,
appearance and session ownership. Physical pinch/Back gestures, screen-reader
interaction and large-text usability still require device evidence.
