# Text Editor

## Try a JSON formatting change

On desktop, open a temporary text file, select `{"a":1}` between other lines and use **Tools → Format JSON**. Undo restores the selection in one step. Change the success caption for **Validate JSON** in `Python/features/text_editor/ui/editing.py:EditingCommands.structured_text`. Add a caption assertion to `test_format_selection_undo_and_failure_preserves_buffer`. From the checkout root, expect the new caption, unchanged validation input and passing format/undo/error cases.

```sh
python3 dev.py test desktop --exact-file Python/tests/editing/test_text_editor_extensions.py
```

## Find the owner

| Change | Owner under `Python/features/text_editor/` |
| --- | --- |
| Launcher, browser actions and settings | `contributions.py` |
| Pane reuse and close | `ui/service.py`, `ui/window.py` |
| Encoding, revisions and worker saves | `ui/document.py`, `ui/file_operations.py` |
| Checkpoints and shortcuts | `ui/session.py`, `ui/commands.py` |
| Mobile managed widgets | `mobile/ui.py` |

Explicit Open in Text Editor preserves ordinary specialized-reader activation. Disable withdraws entry points while open panes remain. [Notes Library provider documents](../../notes_library/development/development.md#notes-document-ownership)

## Save and recover

`commonUtils.persistence.text` preserves BOM, encoding, mixed line endings and no-op bytes. Use explicit conversion for legacy encodings. Writes recheck the disk revision and atomically stage siblings. Missing original requires Save As; creation refuses clobber. Merge Disk Changes validates both buffer and disk, updates the baseline and inserts one undoable edit. Save remains explicit.

LocalCrypt Save As publishes and reopens before handing over the draft. Failure keeps the original. Exclude private text and paths from ordinary recovery. Shutdown waits for the serialized checkpoint. Synchronous capture failure falls back to Save/Discard/Cancel; asynchronous failure keeps the draft for retry. Older checkpoints with only `language` restore it as a manual choice. Shortcut publication failure restores live bindings and saved bytes. See `test_text_editor.py` and `test_text_editor_recovery.py`.

Desktop opens up to 16 MiB with reduced presentation above 1 MiB. JSON/XML operations cap at 1 MiB; XML rejects DTDs/entities and formatting-unsafe structures. Highlighting uses Pygments 2.19.2 (BSD-2-Clause, `PYGMENTS_LICENSE.txt`), with reduced multiline coverage for fallback lexers.

## Mobile editor

`mobile/ui.py` owns managed documents. The host owns picker choices, workspace lifetime and provider sessions. For shared mobile editing, see [Mobile Markdown editing and layout](mobile-markdown-rework.md).
