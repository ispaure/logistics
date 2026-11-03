# Mobile accent design and implementation

## Brief

Appearance provides a compact Accent color group above Seasonal snow on Android
and iOS. Two native sliders expose the full hue spectrum (0–359°) and saturation
(0–100%). A thin spectrum guide sits above Hue. A preview shows selected and ordinary tabs together. Values remain
visible for precise adjustment and assistive technology. Reset to blue restores
the default blue. No brightness control is exposed. The same selected color is
used for accent text and controls in light and dark appearance, without lightening
it for text.

Dragging updates the local preview; releasing saves on this device and refreshes
the application colors. Android uses 64-point control rows and 32-point thumbs.
During a drag, existing native slider artwork is tinted in place. Hue movement
does not redraw the unchanged spectrum; saturation changes update that guide. Failed saves restore
the saved choice and explain the error. Existing installations default to blue.
The layout stacks vertically to fit phone and split-pane settings widths.
Keyboard and accessibility adjustments save on change because they have no touch
release event.

## Color boundary

There is one accent choice for the entire app. Each appearance resolves that
choice once; tabs, controls and actions share the same resolved color, without
regional overrides. Hue and Saturation filled tracks and thumbs preview that
exact opaque color while dragging, matching the selected preview tab. Inactive
track segments remain neutral so the slider position stays clear.

Accent roles color selected navigation tabs, tab indicators, settings commands,
and native control tints. Neutral surfaces and ordinary text retain Slate colors.
File/folder artwork and workspace locked/unlocked roles retain their independent
semantic colors. Destructive controls and document content are also independent.
High contrast / E Ink keeps its black-and-white palette while retaining the saved
accent for use when high contrast is disabled.

## Validation

Host tests cover preference persistence/validation, the spectrum's contrast in
light/dark mode (including selected-row backgrounds), reset, failed-save recovery,
non-touch changes and invariant semantic colors. The default blue and custom accents use identical color values in both appearances;
custom saturation is preserved. User-selected colors have no minimum text contrast
guarantee.

On November 2, 2026, focused disposable iOS and Android native probes passed green
and purple selection, persistence, reset and semantic palette invariants. iOS
screenshots were inspected for the spectrum guide, selected tab/action colors and
switch tint. Both final QA apps and devices were removed; a first failed Android
run required explicit recovery of its owned emulator process. Evidence stays in
ignored test-results storage. Native dark-mode, E Ink, physical-device gestures
and assistive-technology interaction remain outside this focused native scope;
host tests cover the light/dark color calculation and non-touch save contract.

On November 3, a disposable Android touch probe dispatched down, move and up
MotionEvents to both native accent sliders. Both retained their native artwork
throughout dragging, exposed 64 dp control heights and 32 dp thumbs, and refreshed
the application exactly once on release. The probe also passed green/purple color
and reset checks, then removed its owned app and emulator. This verifies emulator
touch dispatch; physical-device touch feel still requires user feedback.
