# Books & Comics integration

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

EPUB reading and direct metadata editing, independent of Calibre, alongside the
existing comic tools under one Books & Comics feature toggle.
Access reading and metadata tools through File Browser; this feature contributes
no main navigation tab.
See the [user guide](../user/user.md) for reading controls, settings and backups.

## Structure

- `epub.py`: Qt-independent archive validation, OPF package metadata, EPUB 3
  navigation and EPUB 2 NCX, spine order, safe archive-relative paths.
- `metadata.py`: targeted Dublin Core updates, namespace preservation, backup
  creation and atomic replacement. Writes serialize within Logistics and reject
  changed-on-disk sources. ZIP resources are streamed without extraction.
- `ui/content.py` / `ui/text_view.py`: inert XHTML conversion and bounded archive-local
  image loading. Script execution, filesystem reads and network resources are
  not delegated to Qt's default resource loader.
- `preferences.py`: shared settings access plus atomic, per-book reading state.
- `ui/reader_controls.py`: compact toolbar, appearance popup, contents/bookmarks
  sidebar and on-demand search. Both readers use `commonUtils.ui.readers.reader_menus`
  for shared menus and bounded recent-file history.
  The EPUB reader opens only EPUBs; the comic reader opens only CBZs. The unified
  feature and browser metadata action do not merge their reading engines.
  `commonUtils.ui.readers.reader_chrome` supplies palette-aware icons, uniform controls,
  elided titles/status and native fullscreen state synchronization. Navigation
  and format-specific controls remain in their own reader modules.
  Shared read-aloud controls start at the top of the visible EPUB page, highlight
  the current word and provide approximate 15-second backward/forward jumps.
- `ui/text_view.py`: screen-height QTextDocument pagination with discrete arrow-key
  turns. The hidden scrollbar represents page offsets, including a short final
  page. Saved locations use a UTF-16 document offset within the spine chapter;
  legacy proportional positions remain a fallback. Font/viewport changes map
  the saved text offset into the new page layout; no whole-book pagination scan
  is required. Search and chapter anchors snap to their containing page.
- `ui/preview.py`: bounded cover decoding for file-browser metadata panels and tile
  thumbnails. Covers resolve via EPUB 3 manifest properties, EPUB 2 metadata,
  or a cover guide/first-page image; images retain their aspect ratio.
- `ui/metadata_actions.py`: dispatches the shared browser metadata action to the
  EPUB or comic editor, including mixed selections, without opening readers.
- `ui/reader.py` / `ui/metadata_editor.py` / `ui/metadata_window.py`: page, reader window,
  reusable metadata form and independent metadata window for browser edit actions.
  Opening and saving use owned `BookTask` workers; close waits for
  worker completion before allowing destruction.
- `contributions.py` / `ui/controller.py` / `file_type.py`: lazy feature declaration,
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

The Aa popup writes sparse personal overrides to the same layered stores used by
Settings: font family/size in shared Styling, other appearance fields in Reader.
Store notifications reload open readers; explicit styling reload updates Markdown
fonts too. Reader Automatic fonts copy QApplication's font instead of constructing
QFont with an empty family, which can resolve to emoji metrics on macOS.

Reading state additionally saves zero-based chapter and total reading-order
chapter counts for cheap thumbnail badges. EPUBFile seeds its spine from the
existing thumbnail worker so legacy path-only state can be resolved without
opening archives while painting. The generic commonUtils badge hook reads only
bounded private reading state, honours remember_position_bool, and omits unread
or malformed records.


`EPUBBook(path, source=provider)` optionally reads a virtual archive through
`source.open(path)` and `source.version(path)`, without resolving a local file.
This supports mobile LocalCrypt reading in RAM. The ordinary filesystem constructor
and metadata-writing workflows are unchanged; source-backed books are read-only.

## Desktop/mobile ownership

`xhtml.py` shares offline named-entity parsing between the Qt and mobile renderers.
`mobile/content.py` owns sanitized HTML and the provider text fallback;
`locations.py` and `mobile/navigation.py` supply text locations, search, nested
contents and chapter labels. `mobile/presentation.py` owns trusted WebView
commands. `mobile/provider_reader.py` reuses that bridge for private rich EPUBs;
`mobile/private_view.py` configures the nonpersistent iOS/Android backend and clears
it on disposal. `mobile/text_reader.py` remains the unsupported-backend fallback.
`mobile/appearance.py` supplies the shared native Books & Comics appearance form.
`mobile/metadata.py` owns field and patch semantics.
Mobile rendering and chapter labels are feature-owned; import records, provider
transactions and session/privacy policy remain host-owned. See the
[parity assessment](books-comics-parity.md) for remaining
reader and editing gaps. Shared parsing does not imply full reading parity.


## Native speech and typography

`mobile/typography.py` owns validated font/spacing/width options and offline CSS;
`themes.py` supplies the canonical colours to both desktop and mobile. Native
fonts are enumerated locally. The host stores preference values and reloads the
current chapter; DOM offsets continue to index the same sanitized text.

`mobile/speech.py` segments bounded UTF-16 utterances and owns generation-checked
play/pause/resume/stop state. `mobile/speech_native.py` adapts AVSpeechSynthesizer
and Android TextToSpeech using installed offline voices. Android progress/error
callbacks are implemented in the feature's `mobile/android/` Java source; the host
build stages that source and merges the feature-owned speech-service query.
`mobile/speech_view.py` owns the inline native controls. Hosts provide current
text/selection and range-follow callbacks, then dispose speech before chapter
replacement or reader retirement. Resume repeats the current bounded utterance.

The trusted DOM bridge preserves selection offsets when native controls take
focus or resize the WebView. Programmatic scroll restoration is distinguished
from user movement so reflow does not replace a precise anchor with the beginning
of its newly wrapped line. No speech text, voice buffer or private selection is
written to the catalogue or recovery records.

## Desktop presentation

Desktop widgets and controllers live in feature-owned `ui/`. Registration stays lazy; portable domain modules do not import this package. IDE/Text Editor change-marker and hunk integration is shared through `services/editors/ui/`.

## Format mutations

`mutations.py` owns metadata plans, content-preserving archive rewrites and post-write format validation for desktop/mobile consumers. Storage adapters retain conflict detection, encryption and atomic publication; the mobile managed library retains recovery journals and checksum records.

## Mobile source manifest

`../../mobile_sources.json` declares this feature's selected portable/mobile sources. Update it when adding an imported module. The build tool aggregates and checks the allowlists without starting desktop registration.

## Native mobile pagination and speech

`mobile/presentation.py` lays sanitized chapter content into fixed-height CSS
columns inside a clipped viewport. Page turns translate by one column; touch
and wheel handlers prevent vertical page scrolling. Resizing rebuilds columns
and seeks the retained UTF-16 text anchor. The same bridge serves imported and
nonpersistent provider WebViews. `mobile/navigation.py` owns nested chapter rows;
the hosts mount them through the shared adaptive sidebar. Search remains an
explicit action outside the chapter list.

`mobile/speech.py` keeps bounded utterances and a private in-memory word-offset
index. Fifteen-second skips use 180 words/minute multiplied by playback speed,
including elapsed time in the current utterance; native synthesis supplies no
seekable audio timeline. Skips invalidate old completion tokens, respect selected
passage bounds and preserve pause state. Stop/disposal clear text and word offsets.
