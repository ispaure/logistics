# Text Editor

Text Editor opens plain text and code in Logistics' desktop document workspace.
The mobile feature opens and creates text, source and Markdown. See the
[desktop user guide](../user/user.md) and [mobile user guide](../user_mobile/user_mobile.md).

## Try a JSON formatting change

On desktop, put the following text in a temporary `.txt` file:

```text
prefix
{"a":1}
suffix
```

Open it with **Documents → Text Editor**, select just `{"a":1}` and choose
**Tools → Format JSON**. Only the selection changes. Undo once to restore it.

Try changing the successful **Tools → Validate JSON** status text in
`Python/features/text_editor/ui/editing.py:EditingCommands.structured_text`.
Add an assertion to `test_format_selection_undo_and_failure_preserves_buffer`
that validating the original selection shows your new status and leaves the
buffer untouched. Use the existing formatter and validator from commonUtils.
Relaunch and validate the same selection to see the new caption.

From the checkout root with the [desktop environment](../../../development/setup/getting-started.md)
set up, run:

```sh
python3 dev.py test desktop --exact-file Python/tests/editing/test_text_editor_extensions.py
```

Expect twelve passing tests. Formatting changes the selection in one undo step,
invalid input leaves the buffer intact, and your validation assertion checks the
new caption and unchanged source.

## Architecture

`Python/features/text_editor/contributions.py:register` declares an optional
`text` document launcher, File Browser actions and settings. The launcher
uses `services.documents.ui.editors` to choose a resource, then opens local
paths through `EditorService`. **Open in Text Editor** is an explicit browser
action. Generic activation preserves specialized readers and Markdown opening.
**Force Open as Text…** provides an explicit path for other files.

| Change | Owner under `Python/features/text_editor/` |
| --- | --- |
| Focus and reuse a document pane, notify browser on save | `ui/service.py` |
| Widget, menu and close lifecycle | `ui/window.py` |
| Snapshot, encoding and per-document metadata | `ui/document.py` |
| Queued load/save, conflict and private handoff | `ui/file_operations.py` |
| Editing, validation, search and status commands | `ui/editing.py` |
| Recovery, command discovery and shortcuts | `ui/session.py`, `ui/commands.py` |
| Syntax selector and settings | `ui/syntax_settings.py`, `preferences.py` |

The shared dock workspace owns outer tabs, splits and detached windows.
An untouched blank can be reused for Open. A canonical local path focuses its
existing pane. Feature disable withdraws entry points and keeps open panes.
[Notes Library](../../notes_library/development/development.md#notes-document-ownership)
has separate embedded documents and provider resources.

## Shared language selection

The [commonUtils language API](../../../../Python/commonUtils/docs/development/reference/formats/formats.md#editor-language-selection)
owns language IDs, catalogues and automatic/manual detection. Desktop
`Document` retains its `LanguageSelection`; mobile binds to CodeInput's
model. Logistics owns status captions and synchronizes highlighting, folding
and comments across both desktop document views. Recovery writes
`language_override` alongside `language`. Older checkpoints with only
`language` restore that effective language as a manual choice. Mobile language
selection lives with the retained editor view.

## Highlighting dependency

Logistics pins pure-Python Pygments 2.19.2. The shared Qt adapter carries
RegexLexer state across text blocks. Extended or delegating lexers, including
YAML and JSON, can use a per-block fallback with reduced multiline coverage.
Unsupported definitions fall back to plain text. The shared adapter includes
the BSD-2-Clause notice in `PYGMENTS_LICENSE.txt`. See the
[Pygments project and license](https://github.com/pygments/pygments).

## File safety and limits

Local reads and writes run in owned workers while Qt handles the UI.
`commonUtils.persistence.text` owns BOM and strict decoding, byte preservation
and atomic sibling staging with conflict rechecks. Legacy encodings and
conversions require explicit selection. Unchanged lines preserve their
individual endings when a mixed-ending document changes. No-op saves retain
the original bytes. A missing original requires Save As. New files use
no-clobber creation. External writers can still race final promotion.

`FileOperations.save_document` captures source, destination revision and
encoding before queueing a write. Save As into LocalCrypt hands off to a
session-only editor after publication and successful reopen. Failure preserves
the original draft. Private drafts and filenames stay out of ordinary editor
recovery. LocalCrypt text opens up to 16 MiB and private Markdown up to 8 MiB.

| Operation | Limit or fallback |
| --- | --- |
| Opening | Simpler presentation above 1 MiB, refusal above 16 MiB |
| Syntax formatting | Skips blocks over 20,000 characters |
| Find | 50,000 matches with Replace All disabled if truncated, occurrence highlights capped at 1,000 |
| Structural folding | Up to 256 KiB and 10,000 lines |
| Diff | Up to 1 MiB and 5,000 lines per side |
| JSON/XML operations | Up to 1 MiB. JSON preserves number and key tokens. XML formatting refuses DTDs/entities, mixed content, CDATA and preserved whitespace. |

### Merge external changes

**Compare → Merge Disk Changes…** uses the loaded or saved snapshot, current
buffer and fresh disk revision. Applying a merge checks that buffer and disk
still match the review, updates the disk baseline and inserts the chosen result
as one undo block. Save remains explicit. Reopen the review if either side
changes. `test_text_editor_extensions.py` covers the merge, comparisons,
undo and stale apply guards.

### Recovery failure during close

Individual close prompts for modified text. Suspension or app shutdown waits
for a durable, private checkpoint and leaves original files untouched. Each
session uses an exclusive lock, serialized writes and atomic publication.
Recovery restores up to 100 documents or 64 MiB, including dirty buffers,
encoding, cursors, split orientation and scroll. Clean files reload from disk.
Dirty files retain the prior save-conflict baseline. Outer docking and detached
window positions are outside the checkpoint.

Synchronous capture/submission failures fall back to Save/Discard/Cancel
immediately. An asynchronous failure keeps the draft available for retry or
ordinary close. Keep a nonempty error state even when the exception has no
message. Test both failure timings in `test_text_editor_recovery.py`.

### Shortcut save failures

`ui/commands.py` owns shortcut overrides. Validate temporary actions and
publish the JSON mapping atomically before notifying other windows. Failure
restores the active bindings and preserves the saved bytes.
`test_text_editor_extensions.py` covers invalid values, failed serialization
and publication failures.

## Mobile editor

`Python/features/text_editor/mobile/ui.py` owns managed document widgets and
commands. The host owns picker choices, session records and workspace lifetime.
Provider Markdown uses shared authoring with provider-scoped access and writes.
Start with [Mobile Markdown editing and layout](mobile-markdown-rework.md) for
WebView changes, mode transitions and device acceptance. Use
`mobile_build/tests/editing/test_source_editor.py` for native input adapters
under the host backend and `test_provider_markdown.py` for provider modes.

## Validation

Run `test_text_editor.py` for browser and editor lifetime, byte preservation
and conflict behavior. Use the extension suite above for commands, saved
shortcuts and split views, and the recovery suite for checkpoint handling.
Shared code input, persistence and editor APIs are tested in commonUtils.
See [test selection](../../../development/testing/testing.md#find-the-tests-for-your-change)
for host profiles and platform checks. Desktop offscreen Qt exercises document
behavior. Native window layout, mouse and keyboard interactions require the
affected desktop platform.
