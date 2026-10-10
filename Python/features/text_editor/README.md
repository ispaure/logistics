# Text Editor

An optional Logistics feature for plain text and code, independent of Books,
Comics and the shared Markdown reader. Open **Settings → Text Editor → Open Text
Editor**, or use **Open in Text Editor** in a browser. Each file has one editor
pane in the application's document workspace, and can detach into its own window.
Reopening a file focuses its existing pane. Disabling the feature removes
contributions while retaining open documents for re-enablement.

## Architecture

| Module | Responsibility |
| --- | --- |
| `contributions.py`, `page.py` | Lazy feature registration, entry point and browser integration |
| `service.py` | Per-document window ownership and browser save notifications |
| `window.py` | Single-document presentation, menus, status and close lifecycle |
| `document.py` | Per-document snapshot, encoding and editing metadata |
| `file_operations.py` | Queued background loads/saves, conflicts and disk notifications |
| `editing.py` | Application commands, nonmodal search integration and status controls |
| `session.py`, `commands.py` | Private recovery checkpoints, safe session restore, command discovery and shortcuts |
| `syntax_settings.py`, `preferences.py` | Language selection and existing INI-based preferences |

The shared dock workspace owns document tabs, splitting and detachment. Editors
have no nested tab bar. File → New opens another document pane; opening a file
reuses an untouched blank document or opens another pane without an extra Untitled
buffer. Each pane retains its existing `OperationProgress` worker and
`RecentFiles` implementation.

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
- Private session checkpoints run in a serialized background executor, with atomic
  replacement and fsync. Per-session QLockFile ownership prevents concurrent-instance
  overwrite/restoration. Closing the last editor releases its recovery writer and
  lock; late document callbacks cannot restart them until another editor opens.
  Original bytes remain the save-conflict baseline for dirty restored files; clean
  files reload current disk content.
- Individual document closure prompts for modified buffers. Application shutdown or
  explicit session suspension waits for the latest durable checkpoint and retains
  buffers without saving originals. Recovery failure falls back to normal prompts.
- Recovery restores editor buffers, two-view orientation, cursors/selections and scroll
  positions on the next editor opening. It does not reproduce the outer workspace's
  dock layout or detached-window placement. Limits: 100 documents / 64 MiB checkpoint;
  edits after the last completed checkpoint can be lost in a crash.
- Diff uses owned background loading/comparison and a reusable side-by-side/unified
  dialog. Applying one change validates the captured buffer and forms one undo block.
  Comparison is capped at 1 MiB / 5,000 lines per side.
- Structural folding is shared across views and bounded to 256 KiB / 10,000 lines.
  Text transformations, multi-cursor commands, format/validation and EditorViews
  remain reusable commonUtils components. XML formatting refuses semantic-risk
  constructs; JSON formatting preserves original number/key tokens.

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


## Additional regression checks

Run `test_text_editor*.py` for feature lifecycle, commands, diff, split views and
recovery failure paths. The reusable `test_code*.py`, `test_session_store.py`,
`test_text_files.py` and `test_workspace.py` suites cover the shared components.
`test_document_workspace.py`, `test_main_window.py` and
`test_application_instance.py` cover surrounding Logistics integration. These are
headless Qt checks run on macOS, Windows, Ubuntu, and Fedora 43 in CI; native
desktop interaction still benefits from manual validation. New UI surfaces have also been rendered and inspected in both themes.
