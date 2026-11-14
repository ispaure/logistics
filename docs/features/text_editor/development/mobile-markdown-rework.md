# Mobile Markdown editing and layout

Use this guide when changing the reading or editing surface shared by managed
Markdown, provider documents and Notes Library on Android and iOS. Start with
[Text Editor development](development.md) for standalone source editing and
[Notes Library lifecycle](../../notes_library/development/development.md#mobile-browsing-and-document-lifecycle)
for library navigation.

## Trace a mode change

Open a disposable local Markdown file from Files or Documents on mobile. Start
with a heading, one paragraph containing `**bold**`, and a fenced code block.
The reader opens in Preview. Select the pencil to enter Formatted editing,
append a word, then use **••• → Source editing** to see its Markdown.
Save and reopen. The changed paragraph is present and untouched blocks retain
their source. Repeat through the unlocked LocalCrypt route when changing access
or resource lifecycle.

| Surface | Owner under `Python/` |
| --- | --- |
| Managed document widgets and preview lifecycle | `features/text_editor/mobile/ui.py` |
| Provider mode, render tokens, search/speech and control callbacks | `services/documents/authoring/provider_markdown.py:ProviderMarkdown` |
| Host injection and provider persistence | `mobile/composition/presentation.py`, mobile provider sessions |
| Block mapping, change bridge and surface retirement | `services/documents/authoring/markdown_editor.py:FormattedMarkdownInput` |
| Browser input, serialization and toolbar commands | `services/documents/authoring/markdown_script.py` |
| Live delimiters and caret intervals | `services/documents/authoring/markdown_live_script.py` |
| Reading typography and editor viewport | `services/documents/authoring/markdown_style.py` |

## Storage and write permissions

`Python/services/documents/access.py:can_write` checks the provider and reader.
Local and unlocked LocalCrypt can save through the selected location.
Cloud remote Markdown opens in a reader, including encrypted remotes and
downloads held by a read-only reader. Enforce authorization in persistence
as well as commands. Provider lock or replacement invalidates pending
publication and retires private WebViews. Private rendered and formatted
surfaces use the memory-only WebView on supported platforms.

## Reading and writing design

One source input holds the draft used by save, search and recovery. Flush
the live Formatted DOM before switching modes, saving or closing. Navigation
messages carry a per-load token. Asynchronous rendering also checks the source,
chosen mode, access and live document before presenting a result. Retain the
draft on save failure and dispose the old surface when replacing the document.
A managed document owns separate preview and formatted WebViews so opening one
document cannot replace another's page. Preview loads after attachment.
Identical rendered HTML retains the existing DOM and scroll.

The offline Formatted surface preserves untouched block syntax, with Source
available for unsupported syntax. Formatted and Source are exclusive. Older
split preferences are retired on load. Delimiter intervals come from
commonUtils Markdown editing rules. The WebView handles UTF-16 ranges,
composition completion, selection and scrolling. Live span rebuilds use an
editor-owned undo history bounded to 100 entries and approximately 8 MiB,
retaining at least the latest edit. The native Source input keeps its own undo.
The link dialog captures the editable range before moving focus and restores
it on confirmation or cancellation.

Markdown sizes use CSS pixels in rendered and formatted views. Native CodeInput
converts the same value to Toga font units. Plain text and EPUB have separate
size policies. Apple uses system font names and Android can follow its device
font through the `sans-serif` fallback. Reading and editing share heading,
code and table proportions.

## Keyboard and adaptive layout

The editor has one scrolling document area and a toolbar outside that area.
In a very short viewport, use the Format overlay. Use the native pane geometry
and visual viewport to avoid duplicate keyboard clearance. The caret check
coalesces updates and scrolls only enough to bring the cursor into view. A
trailing editable region makes a blank note tappable. Touching formatted input
should keep typing, selection, status and navigation usable while the
software keyboard is open.

### In-place library documents

`features/notes_library/mobile/library_document.py` embeds the shared controls
over a provider resource in the retained library session. Its transition flushes
the current view and resolves Save/Discard/Cancel before handing off to the
new document. The [library lifecycle](../../notes_library/development/development.md#mobile-browsing-and-document-lifecycle)
owns history, pending opens and draft retention.

## Testing and acceptance

From the checkout root with the [test environments](../../../development/testing/testing.md)
set up, run the focused mobile host and browser checks:

```sh
python3 dev.py test mobile --exact-file mobile_build/tests/editing/test_provider_markdown.py
python3 dev.py test desktop --exact-file Python/tests/test_mobile_markdown_editing_dom.py
```

Expect provider tests to cover guarded presentation, cancellation and retirement,
and browser tests to cover production HTML, delimiter intervals, undo and
composition. The browser tests use Qt WebEngine. Use `test_markdown_access.py`
when changing authorization, `test_markdown_editor.py` for block/bridge
behavior, and `test_markdown_font.py` for font binding. Package allowlist and
fresh startup checks cover the staged authoring modules.

### Remaining acceptance gates

For native checks, use the managed `document_storage_tools` runner.
`editor-keyboard` exercises keyboard and caret geometry. The iOS
`markdown-typography` probe measures reader, Formatted, Source and Help fonts.
Use `notes-markdown-feedback` for in-library editor transitions. For a
disposable iOS simulator with a current app build, the separate
`mobile_build.validation.markdown_rework_tools` runner exercises native formatting,
save of final input, rotation, LocalCrypt and read-only remotes. See
[mobile commands](../../../development/build-release/mobile-launchers.md) and
[local validation artifacts](../../../development/testing/validation-artifacts.md).

Check the affected platform's real software keyboard, caret, selection, and
reachable Save and mode controls. Use narrow iPad windows and the dedicated
Duo runtime for their particular layouts. Physical input, fold transitions,
autocorrect, dictation and spoken accessibility need native checks where they
affect the change.
