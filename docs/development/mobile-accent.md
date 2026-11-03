# Mobile accent design and implementation

## Brief

Appearance provides a compact Accent color group above Seasonal snow on Android
and iOS. Two native sliders expose the full hue spectrum (0–359°) and saturation
(0–100%). A thin spectrum guide sits above Hue. A preview shows selected and ordinary tabs together. Values remain
visible for precise adjustment and assistive technology. Reset to blue restores
the existing light/dark defaults. No brightness control is exposed: the app
chooses lightness for readable text in each appearance.

Dragging previews the color; releasing saves on this device. Failed saves restore
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
non-touch changes and invariant semantic colors. The default blue retains the
existing light/dark values; custom accents reach 4.5:1 against app surfaces.

On November 2, 2026, focused disposable iOS and Android native probes passed green
and purple selection, persistence, reset and semantic palette invariants. iOS
screenshots were inspected for the spectrum guide, selected tab/action colors and
switch tint. Both final QA apps and devices were removed; a first failed Android
run required explicit recovery of its owned emulator process. Evidence stays in
ignored test-results storage. Native dark-mode, E Ink, physical-device gestures
and assistive-technology interaction remain outside this focused native scope;
host tests cover the light/dark color calculation and non-touch save contract.
