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
`Mobile/cloud_build.py` also refreshes the configured Java source roots in reused
Gradle projects: Briefcase's source update alone does not apply newly added roots.
Without this refresh, older projects can omit `BookSpeechListener` and report
that speech support is missing even with an installed system voice.
`mobile/speech_view.py` owns the floating native controls.
`logisticsmobile/speech_overlay.py` hosts them in a detached iOS container or
Android popup, leaving the document layout tree unchanged. Disposal detaches the
surface. Both native hosts size the popup to its status message and controls,
expanding for wrapped errors and shrinking again for short playback messages.
Settings owns the persisted `speech_voice` preference and loads installed
offline voices on demand, releasing its temporary engine afterward. Playback
resolves the saved voice against the current installed voices and falls back to
the system default when unavailable. Markdown and EPUB share
one playback button, which toggles play/pause and resumes without reloading the
source text; stop and completion restore its play icon. Hosts provide current
text/selection and range-follow callbacks, then dispose speech before chapter
replacement or reader retirement. Resume repeats the current bounded utterance.

Android initializes audio attributes after `onInit` succeeds and prefers the
system's current installed offline voice. Null voice-feature sets are accepted;
network and uninstalled voices are excluded. Voice discovery also checks the
engine's current/default voice when enumeration is empty, incomplete or fails;
the same offline/install checks apply. Malformed individual entries are skipped.
An empty result leaves the picker and Play disabled and explains how to install
voice data in phone settings, then reopen the panel. `onRangeStart` and Apple's
`willSpeakRangeOfSpeechString` forward UTF-16 word ranges onto the application
loop. Session generation checks reject late start/range/completion events after
pause, skip, stop or disposal. Android engines without range events use estimated
word timing starting at the native audio-start event; native ranges cancel it.
Apple uses native ranges throughout. Stop/completion clear the speech highlight.

EPUB uses a separate DOM speech highlight so playback does not become the next
user-selected passage. Markdown builds an in-memory rendered-text node map,
including inline formatting and block separators, and applies those same UTF-16
ranges to its DOM. The map is removed when controls close. Preview-read failures
show a recoverable error instead of escaping the Play handler.

`Mobile/native_tests/tests/logisticsmobile/speech_probe.py` is an isolated-bundle
probe of the real Markdown preview Play handler and EPUB bridge, native range
callbacks, visible word highlights and completion cleanup. Android emulator and
iPhone simulator runs completed both passages with native word events and DOM
highlights during this change. Desktop shared read-aloud and Books reader tests
also pass; Windows/Linux speakers and physical-device audio remain unverified.

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

## System speech controls and privacy

`mobile/media_controls.py` arbitrates one active speech session per process.
`media_ios.py` uses a playback/spoken-audio AVAudioSession, public MediaPlayer
remote commands and generic Now Playing metadata; the host declares the audio
background mode. `media_android.py` connects to the non-exported
`SpeechMediaService`, which owns a media-playback foreground service, MediaSession,
MediaStyle notification, audio focus and a bounded wake lock. No text, document
path or credential label enters metadata, intents or notification storage.
Commands are generation-bound; stopped/revoked sessions cannot resume through
a stale notification. The service is not sticky and never reconstructs speech
after process death.

The host supplies the source credential gate and live credential-generation
check to ReadAloudPanel. Default session-only playback stays foreground-only.
ScreenPrivacy enforces denial synchronously on background/lock; late DOM reads
are checked again before speech starts. A saved device preference permits only
the existing in-memory speech passage while its gate remains locked. Credential
revocation remains authoritative. UI-hidden memory trimming retains only that
single authorized playback owner; navigation/close still disposes it.
