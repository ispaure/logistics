# Mobile accent controls

**Settings → Appearance → Accent color** uses `mobile/settings/appearance.py`
and `mobile/appearance.py`. Drag previews; release saves. Keyboard/accessibility
changes save immediately. Failure restores the previous choice. Reset restores
blue. Semantic colors, high contrast and E Ink use their own palette.

Run `python3 dev.py test mobile 'test_appearance.py'` for saved appearance and
palette behavior. Verify slider touch and accessibility on native platforms.
