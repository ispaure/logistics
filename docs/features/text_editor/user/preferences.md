# Text Editor preferences

Open **View → Logistics Settings…** from an editor. Under
**Feature settings → Text Editor → Options**, configure indentation width,
tabs/spaces, wrapping, line numbers, whitespace, syntax highlighting, automatic
indentation and bracket/quote pairing. Shared code font family and size belong
under **Appearance & shared controls → Styling** and also affect IDE, Git hunks
and Markdown code blocks.

Choose personal settings for private overrides, then **Save Settings**. Use the
**↶** control on a personal field to restore inheritance from software defaults.
Software defaults come from `Python/features/text_editor/config.ini`; the normal
app stores personal editor settings and window geometry in its persistent personal
INI. Font settings use the shared styling store. The old
`Cache/TextEditor/preferences.ini` is a migration source, not the normal active
settings file. Existing private font/editor values migrate once without replacing
already configured personal values.

Recent paths remain in private `Cache/TextEditor/recent.json`. Unsaved text is
stored separately in private session checkpoints, not in preferences or recent
history. See [editor recovery](user.md#appearance-and-preferences) for recovery
limits and shutdown behavior. Session-only LocalCrypt documents do not use these
ordinary recovery/recent records.

These are desktop settings. Mobile uses the
[mobile editor](../user_mobile/user_mobile.md) and its device-local reading and
editing settings; it does not share desktop preference files.
