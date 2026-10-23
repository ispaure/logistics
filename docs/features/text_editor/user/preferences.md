# Text Editor preferences

## Text Editor preferences

`Python/features/text_editor/config.ini` supplies typed editor defaults. Font,
indentation, wrap, gutter, whitespace, syntax and automatic editing choices made
in the window are persisted in `commonUtils/Cache/TextEditor/preferences.ini`,
using the same shared INI APIs. Private overrides take precedence over feature
defaults. **Reset Editor Preferences** removes the overrides. Recent paths use
`recent.json` in the same cache folder; window geometry is stored in the private
INI. Unsaved document content is not stored in preferences or recent history, but is
stored separately in private session checkpoints. See
[editor recovery](user.md#appearance-and-preferences)
for recovery limits and shutdown behavior.
