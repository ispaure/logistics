# Text Editor

An optional Logistics feature for plain text and code, independent of Books,
Comics and the shared Markdown reader. Open its navigation tab, then **Open Text
Editor**, or use **Open in Text Editor** in a browser. One QApplication-owned
service reuses the document window across browser hosts. Disabling the feature
removes contributions while retaining open buffers for re-enablement.

## Architecture

| Module | Responsibility |
| --- | --- |
| `contributions.py`, `page.py` | Lazy feature registration, entry point and browser integration |
| `service.py` | Shared window ownership and browser save notifications |
| `window.py` | Native document tabs, menus, status and close lifecycle |
| `document.py` | Per-document snapshot, encoding and editing metadata |
| `file_operations.py` | Queued background loads/saves, conflicts and disk notifications |
| `editing.py` | Application commands, nonmodal search integration and status controls |
| `syntax_settings.py`, `preferences.py` | Language selection and existing INI-based preferences |

The existing dock workspace targets browser layouts rather than editor document
lifecycles. This feature uses Qt's `QTabWidget` for closable, draggable document
tabs and adds middle-click closure. It uses the existing `OperationProgress`
worker ownership and `RecentFiles` implementation rather than duplicating them.

Reusable Qt-independent file IO lives in `commonUtils.text_files`. The shared
`commonUtils.ui.code_editor` package supplies the gutter, code editing, search
and syntax components; it imports no Logistics modules. Existing public text,
INI, Markdown, EPUB and comic APIs retain their behavior. No file-type registry
rules are replaced. Conditional generic activation preserves specialized
non-text file handling and the built-in Markdown reader; explicit text-editor
opening remains available for Markdown and other text formats.

## Highlighting dependency

Logistics pins pure-Python **Pygments 2.19.2** in its project and lockfile. Its
maintained language definitions support the requested languages and additional
manual choices without Qt ABI or platform binaries. It uses BSD-2-Clause licensing;
the shared adapter includes attribution in `PYGMENTS_LICENSE.txt`.
See [Pygments architecture](https://pygments.org/docs/quickstart/) and
[project source/license](https://github.com/pygments/pygments).

The incremental Qt adapter carries RegexLexer state between text blocks and
rehighlights affected blocks. The compiled-rule adapter is version-specific and
covered by the pinned-version tests. Extended/delegating lexers (including YAML
and JSON) use per-block fallback; their complex multiline constructs may have
less complete highlighting. Highlighting never parses or executes application
code. Unsupported definitions fall back to plain text.

## File safety and limits

- Reads and encoded writes run in owned workers; widget updates remain on Qt's GUI thread.
- Strict UTF decoding recognizes BOMs. Legacy encodings require explicit selection;
  byte replacement is never automatic. Forced binary opening is explicit.
- No-op saves preserve bytes, including BOMs, mixed endings and final newlines.
  Changed lines use the file's detected dominant ending; aligned unchanged mixed
  lines retain their own endings. Unicode paragraph separators survive Qt normalization.
- Encoding/line-ending conversions happen only after an explicit user choice.
- Atomic sibling staging, fsync, original permissions and conflict rechecks protect
  saves. A deleted original requires Save As. Symlinks resolve to their targets;
  canonical paths prevent duplicate tabs for the same resolved path.
- New destinations use no-clobber creation. As with other atomic rename workflows,
  an arbitrary external process can still race the final filesystem promotion.
- Files above 1 MiB use simpler presentation; files above 16 MiB are refused.
  Blocks above 20,000 characters skip syntax formatting. Search stops at 50,000
  matches and disables Replace All when truncated; occurrence highlighting caps
  at 1,000 matches and is omitted for large files. Regex patterns have PCRE resource limits.
- No automatic tab/session restore, autosave or crash-recovery journal is provided.
  Normal tab/window closure always prompts for modified buffers.

## Validation

From the checkout root:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=Python .venv/bin/python -m unittest discover -s Python/tests -p test_text_editor.py -v
QT_QPA_PLATFORM=offscreen PYTHONPATH=Python .venv/bin/python -m unittest discover -s Python/commonUtils/tests -p 'test_code*.py' -v
PYTHONPATH=Python .venv/bin/python -m unittest discover -s Python/commonUtils/tests -p test_text_files.py -v
```

Tests cover byte preservation, legacy and Unicode encodings, conflicts, binary
handling, queue/window lifetime, shared browser activation, feature toggles,
search/replace undo, language definitions and theme-safe presentation. macOS Qt
offscreen testing and rendered layout inspection are available here. Windows and
Linux behavior uses Qt/stdlib APIs and code review; native desktop validation on
those platforms remains separate.
