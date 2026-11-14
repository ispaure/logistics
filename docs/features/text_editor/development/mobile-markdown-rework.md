# Mobile Markdown editing and layout

On Android or iOS, open a disposable Markdown file, enter Formatted with the pencil, edit a paragraph and switch to Source. Save and reopen. Expect the edit and unchanged surrounding source.

| Change | Owner under `Python/` |
| --- | --- |
| Managed widgets | `features/text_editor/mobile/ui.py` |
| Provider mode and render admission | `services/documents/authoring/provider_markdown.py` |
| Block mapping and retirement | `services/documents/authoring/markdown_editor.py` |
| DOM commands, delimiters and typography | `services/documents/authoring/markdown_{script,live_script,style}.py` |

Flush Formatted DOM before mode changes, save or close. One source draft serves search, recovery and save. Guard renderer results by token, source, mode, access and document identity. Preserve failed drafts and untouched blocks. Retire older split preferences. Keep one document scroll area, an external toolbar or short-height overlay, and viewport-aware caret scrolling.

`services/documents/access.py:can_write` admits local and unlocked LocalCrypt writes. Cloud readers stay read-only through persistence. Lock retires private memory-only views. [Notes Library lifecycle](../../notes_library/development/development.md#mobile-browsing-and-document-lifecycle)

```sh
python3 dev.py test mobile --exact-file mobile_build/tests/editing/test_provider_markdown.py
python3 dev.py test desktop --exact-file Python/tests/test_mobile_markdown_editing_dom.py
```

Expect guarded publication and production DOM undo/composition. Check native caret, selection and reachable controls through `editor-keyboard`, iOS `markdown-typography` and `notes-markdown-feedback`. [Mobile commands](../../../development/build-release/mobile-launchers.md)
