# Books & Comics integration

EPUB reading and direct metadata editing, independent of Calibre, alongside the
existing comic tools under one Books & Comics feature toggle.
Access reading and metadata tools through File Browser; this feature contributes
no main navigation tab.
See the [user guide](user_docs/index.md) for reading controls, settings and backups.

## Structure

- `epub.py`: Qt-independent archive validation, OPF package metadata, EPUB 3
  navigation and EPUB 2 NCX, spine order, safe archive-relative paths.
- `metadata.py`: targeted Dublin Core updates, namespace preservation, backup
  creation and atomic replacement. Writes serialize within Logistics and reject
  changed-on-disk sources. ZIP resources are streamed without extraction.
- `content.py` / `text_view.py`: inert XHTML conversion and bounded archive-local
  image loading. Script execution, filesystem reads and network resources are
  not delegated to Qt's default resource loader.
- `preferences.py`: shared settings access plus atomic, per-book reading state.
- `reader_controls.py`: compact toolbar, appearance popup, contents/bookmarks
  sidebar and on-demand search. Both readers use `commonUtils.ui.reader_menus`
  for shared menus and bounded recent-file history.
  The EPUB reader opens only EPUBs; the comic reader opens only CBZs. The unified
  feature and browser metadata action do not merge their reading engines.
  `commonUtils.ui.reader_chrome` supplies palette-aware icons, uniform controls,
  elided titles/status and native fullscreen state synchronization. Navigation
  and format-specific controls remain in their own reader modules.
- `text_view.py`: screen-height QTextDocument pagination with discrete arrow-key
  turns. The hidden scrollbar represents page offsets, including a short final
  page. Saved locations use a UTF-16 document offset within the spine chapter;
  legacy proportional positions remain a fallback. Font/viewport changes map
  the saved text offset into the new page layout; no whole-book pagination scan
  is required. Search and chapter anchors snap to their containing page.
- `preview.py`: bounded cover decoding for file-browser metadata panels and tile
  thumbnails. Covers resolve via EPUB 3 manifest properties, EPUB 2 metadata,
  or a cover guide/first-page image; images retain their aspect ratio.
- `metadata_actions.py`: dispatches the shared browser metadata action to the
  EPUB or comic editor, including mixed selections, without opening readers.
- `reader.py` / `metadata_editor.py` / `metadata_window.py`: page, reader window,
  reusable metadata form and independent metadata window for browser edit actions.
  Opening and saving use owned `BookTask` workers; close waits for
  worker completion before allowing destruction.
- `contributions.py` / `controller.py` / `file_type.py`: lazy feature declaration,
  feature-owned EPUB type and browser-window lifetime management.

The `books` and `comics` runtime IDs, module paths and existing comic APIs remain
available. `FEATURE_GROUP = 'books'` groups the comic engine into the Books &
Comics settings entry; enable/disable applies to both engines together. Calibre
remains separate. Settings panels retain each engine's own configuration files.
The optional `SelectionAction.shared_key` allows the browser to deduplicate the
cross-format metadata command while leaving other action identities unchanged.

There are no new dependencies. Settings
live directly in `config.ini` and use the shared typed INI editor. Reading state
uses a SHA-256 key of the canonical absolute book path under `commonUtils/Cache/Books`.
Archive limits: 512 MiB uncompressed total, 20,000 entries, 32 MiB per read
resource; image decoding checks dimensions before reading pixel data.

Metadata saves preserve unknown metadata/comments, identifiers and retained node
IDs, clear outdated `file-as` refinements when values change, and update EPUB 3's
`dcterms:modified`. OPF formatting/prefix spelling can change during serialization.
Edited signed books may require signing again. Atomic staging stays beside the
EPUB so replacement is on the same filesystem; the source's permissions are kept.
The backup must complete before replacement. Failure/cancellation cleans staging
and leaves the source unchanged. External-process conflicts are checked using
filesystem identity, size and nanosecond timestamps before replacement.

The package model, metadata writer and reader controls are independently tested
using generated EPUB fixtures. Run from the checkout root:

```sh
PYTHONPATH=Python python -m unittest discover -s Python/tests -p 'test_books*.py'
```

Implementation follows the [EPUB package/navigation model](https://www.w3.org/TR/epub-33/)
and Qt's [rich-text browser resource hooks](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QTextBrowser.html).
