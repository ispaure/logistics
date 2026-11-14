# Mobile accent controls

Start at **Settings → Appearance → Accent color** on Android or iOS. Edit
`Python/mobile/settings/appearance.py` for the controls and
`Python/mobile/appearance.py` for color roles. Hue spans 0–359° and saturation
spans 0–100%. Reset restores the default blue.

Drag previews locally. Release saves and applies the color to both appearances.
Keyboard and accessibility adjustments save on change. A failed save restores
the prior choice and reports the error. Android uses 64 dp rows and 32 dp
thumbs and tints existing slider artwork in place during drag.

## Color boundary

Each appearance resolves one app accent. Tabs, native controls, Settings
commands and destination confirmations take that color. File/folder icons,
lock state, destructive actions and document content retain their semantic
colors. High contrast and E Ink keep their own palette while remembering the
saved accent. User-selected colors have no minimum text contrast guarantee.

## Validation

From the repository root run:

```sh
python3 dev.py test mobile --exact-file mobile_build/tests/workspace/test_appearance.py --exact-file mobile_build/tests/workspace/test_settings_ui.py
```

Expect the host checks to preserve the selected color, drag/release behavior,
reset, failure recovery and semantic roles. For a native control change, check
actual slider touch and accessibility delivery with a managed QA payload.
