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
  Manual page turns also discard resize anchors queued during outgoing-page
  capture, so a later layout change preserves the newly selected page.
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
Loads read at most 128 KiB plus one byte before JSON parsing; oversized or malformed
records return the existing empty state without changing the file. Saves enforce
the same encoded-byte limit before publication, preserving the previous checkpoint
on oversized bookmark data. The reader reports the existing save error feedback.
Archive limits: 512 MiB uncompressed total, 20,000 entries, 32 MiB per read
resource; image decoding checks dimensions before reading pixel data.

Metadata saves preserve unknown metadata/comments, identifiers and retained node
IDs, clear outdated `file-as` refinements when values change, and update EPUB 3's
`dcterms:modified`. OPF formatting/prefix spelling can change during serialization.
Edited signed books may require signing again. Atomic staging stays beside the
EPUB so replacement is on the same filesystem; the source's permissions are kept.
The backup must complete and match the SHA-256 of the copied original bytes
before replacement. Backup changes during verification or corrupted copies
abort publication and remove the failed backup only while it retains the identity
of the exclusively created file. A replacement file/link is preserved and cannot
admit publication, even with identical bytes. Identity checks are optimistic;
they do not lock out external writers or attribute same-file in-place edits. Failure/cancellation cleans staging
and leaves the source unchanged. External-process conflicts are checked using
filesystem identity, size and nanosecond timestamps before replacement.

`ui/reader_controls.py` keeps `build_controls(page)` as the composition entry point.
Its private builders group menus, header, appearance, sidebar, reading area and
footer in the same module. Controls, callbacks, speech/spread ownership and legacy
widget handles stay on the page; construction order and external-menu embedding
remain unchanged. Reader navigation/loading and persisted state stay in their
existing owners.

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
commands. The bridge permits the native WebKit `about:blank` bootstrap only
before its chapter load completes; external URLs, stale chapter callbacks and
blank-page variants remain blocked. Next/Previous events wait for pending
position writes before changing chapters. These policy contracts are checked by
`test_epub_load_policy.py` and `test_epub_boundary_flush.py`; actual rendered
chapter replacement still requires native acceptance.
`mobile/provider_reader.py` reuses that bridge for private rich EPUBs;
`mobile/private_view.py` retains the Books HTML byte policy over the shared
nonpersistent native WebView, which clears content on disposal. `mobile/text_reader.py` remains the unsupported-backend fallback.
`mobile/appearance.py` supplies the shared native Books & Comics appearance form.
`library/metadata.py` owns portable field/patch and catalogue mapping semantics;
`mobile/metadata.py` preserves its compatibility imports.
Mobile rendering and chapter labels are feature-owned; import records, provider
transactions and session/privacy policy remain host-owned. See the
[parity assessment](books-comics-parity.md) for remaining
reader and editing gaps. Shared parsing does not imply full reading parity.


## Native speech and typography

`mobile/typography.py` owns validated font/spacing/width options and offline CSS;
`themes.py` supplies the canonical colours to both desktop and mobile. Native
fonts are enumerated locally. The host stores preference values and reloads the
current chapter; DOM offsets continue to index the same sanitized text.

`mobile/speech.py` and `speech_native.py` preserve existing imports over reusable
commonUtils speech sessions and native engines. The shared native Java root owns
progress/error callbacks; the feature retains media controls, Android service
resources and the speech-service query. `mobile/speech_host.py` declares explicit
icon, overlay, saved-voice and playback factories; `speech_view.py` imports no
mobile application modules. The host composes its existing presentation and
locked-session policy through those factories.
`mobile_build/cloud_build.py` also refreshes the configured Java source roots in reused
Gradle projects: Briefcase's source update alone does not apply newly added roots.
Without this refresh, older projects can omit the shared `SpeechListener` and report
that speech support is missing even with an installed system voice.
`mobile/speech_view.py` owns the floating native controls. Speed uses a native
seven-detent slider over 0.5–2.0, snapping to 0.25 increments, with muted percent
limits, tick markers and a live percent label. The timer row pairs the duration
with an accessible reset icon; a separate bold label shows its remaining time.
Playback buttons share the available row width and status text sits below them.
The overlay height includes the section spacing and grows for wrapped status
messages. `test_speech_overlay` covers slider quantization and timer behavior;
`speech_controls_probe` checks native control bounds with a silent fixture engine.
`mobile/speech_overlay.py` hosts them in a detached iOS container or
Android popup, leaving the document layout tree unchanged. Disposal detaches the
surface. Both native hosts size the popup to its status message and controls,
expanding for wrapped errors and shrinking again for short playback messages.
Settings owns the persisted `speech_voice` preference and loads installed
offline voices on demand, releasing its temporary engine afterward. Playback
resolves the saved voice against the current installed voices and falls back to
the system default when unavailable. Markdown and EPUB share
one playback button, which toggles play/pause and resumes without reloading the
source text; stop and completion restore its play icon. Speed changes re-synthesize
from the current word with a fresh generation, or update the rate for a paused
session's next resume. An outside tap detaches only the overlay; iOS observes taps
outside its native subtree without consuming them, and Android uses a focusable,
outside-touchable popup with a dismissal callback. Teardown removes the observer
or callback before releasing the native surface. Hosts reuse
the panel when reopening controls and retain session disposal for reader teardown.
`PlaybackTimer` in `mobile/speech.py` owns a monotonic listening-time budget.
The panel forwards speaking/paused/stopped transitions, including system media
commands, without resetting the budget at utterance boundaries or speed changes.
An event-loop callback refreshes the remaining-time label at most once per second
and pauses the session at expiry; elapsed time is measured against a deadline,
so delayed callbacks do not extend the budget. Reset and duration changes restore
the selected budget in the current playback state. Play after expiry starts a
fresh budget. Hiding the overlay leaves the timer active; disposal cancels its
callback. The timer defaults to Off and is not persisted.
`SpeechPlayback.timer_changed` forwards the displayed countdown to an existing,
allowed native media owner and caches it for initial metadata publication.
iOS uses the Now Playing artist/subtitle field; Android uses media-session artist
and display-subtitle metadata plus notification content text. Timer refreshes
update metadata without reactivating audio, requesting focus, renewing a wake
lock or recreating system controls. Android refreshes the existing notification;
playback transitions retain foreground-service ownership. Public reader hosts
opt in through `document_title`: metadata uses only its basename (up to 120
characters), without reading or forwarding utterance text to the native adapters.
The subtitle contains only the listening timer or app name. Private hosts leave
the title provider empty; credential-session sources remain generic regardless of
the background-audio opt-in. The OS controls subtitle presentation and refresh timing.
Hosts provide current
text/selection and range-follow callbacks, then dispose speech before chapter
replacement or reader retirement. Resume continues from the current word.

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
user-selected passage, including on engines using the native selection fallback.
Speech highlighting seeks the word's column without stopping synthesis. New
playback queries the DOM's visible page start and current selection, so Stop/Play
starts at the current page rather than the last spoken word. Markdown builds an in-memory rendered-text node map,
including inline formatting and block separators, and applies those same UTF-16
ranges to its DOM. The map is removed when the speech owner is disposed. Preview-read failures
show a recoverable error instead of escaping the Play handler.

`mobile_build/native_tests/tests/logisticsmobile/speech_probe.py` is an isolated-bundle
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

The mobile host's `ReaderController.open_book` reloads the current chapter on
explicitly reopening an already loaded imported EPUB. A retained archive decoder
does not establish that the native WebView still has its document. Reopen waits
for pending position writes through `move_book_page`, replaces the chapter bridge
and restores the saved passage without creating another session or import.
`mobile_build/tests/reading/test_reader_sessions.py` covers this recovery path. Switching
destinations alone does not trigger a chapter reload.

`mobile/speech.py` keeps bounded utterances and a private in-memory word-offset
index. A skip retires the old generation and publishes a clear range before
stopping the old native utterance; synchronous/late callbacks cannot repaint it.
Both EPUB and Markdown empty the old CSS `Highlight` before deleting its registry
entry so WebKit also invalidates its painted ranges. The silent native
`speech_skip_probe` verifies eight EPUB/Markdown forward/backward cases while
playing and paused, including empty old range objects and exactly one new range.
Desktop `test_books_reader` covers mirrored spread cleanup; shared speech tests
cover matching slider/timer behavior without using speakers. Fifteen-second skips use
180 words/minute multiplied by playback speed,
including elapsed time in the current utterance; native synthesis supplies no
seekable audio timeline. Skips invalidate old completion tokens, respect selected
passage bounds and preserve pause state. Stop/disposal clear text and word offsets.

## System speech controls and privacy

`mobile/media_controls.py` arbitrates one active speech session per process.
`media_ios.py` uses a playback/spoken-audio AVAudioSession, public MediaPlayer
remote commands and Now Playing metadata; the host declares the audio
background mode. `media_android.py` connects to the non-exported
`SpeechMediaService`, which owns a media-playback foreground service, MediaSession,
MediaStyle notification, audio focus and a bounded wake lock. Ordinary imported
EPUBs, ordinary Markdown previews, public vault notes and documentation publish
a filename alongside the timer; document passages never enter native metadata. Private
sources publish only generic metadata and timer information, even with background
speech enabled. Full paths and credential labels are excluded, and command
intents never carry document text.
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

## Mobile sidebar allocation

Imported and provider EPUB chapter browsers scroll their padded tree, bookmarks
and session notice together inside an unpadded sidebar viewport. Its 44-point
minimum permits short landscape panes without fixed bookmark controls expanding
the entire reader beyond the safe area. The adaptive sidebar's fixed width includes
that internal padding, so the calculated text width stays within the native safe area
when switching orientation. The mobile native release suite checks portrait and
both landscape directions repeatedly, retaining the active reader and chapter
browser state.

## Reading and library controller ownership

`mobile/reader_controller.py` owns imported EPUB page preparation, location-flush
state/tasks, link/boundary navigation, chapter search and width observation.
`mobile/provider_controller.py` owns provider EPUB tools and width-task state.
Host compatibility accessors delegate to these owners, including deletion during
suspension; state publication uses setters rather than bypassing them with a
`__dict__` update. Host services supply layout events, themed HTML and lifecycle
identity; storage, credential checks and writer ownership remain in Logistics.

`library/index.py` owns the existing ordinary-import SQLite cache and its unchanged
schema. `library/metadata.py` supplies bounded per-format metadata loaders.
`mobile/library/catalog.py` owns mixed library filtering and incremental refresh,
with `LibraryHost` callbacks for discovery snapshots, routing and presentation.
Discovery itself stays in the host. Protected metadata is excluded from indexing.
The catalogue and reader controllers retain their own tasks and generation guards.


## iOS catalogue toolbar

The catalogue declares Refresh and Import as screen-level iOS actions, with
symbols and accessible titles. The host detaches these retained controls from
the header and mounts ordinary UIKit bar items, including Duo vertical bars.
Empty-state entry points and library-row actions remain in content. The reader
uses the host's separate native reader action contract. Android retains its
catalogue header.

## Mobile EPUB motion policy

The host supplies `motion_enabled` when creating either imported or private
chapter views, including the native text fallback. Rich EPUB bridges include the
flag in their initial script options and expose `set_motion_enabled` for retained
readers. Theme/contrast refresh sends the current preference to every retained
bridge before backend-specific styling. A false policy cancels a running Web
Animation and suppresses subsequent turns, independently of Android's HTML
contrast marker. The bridge still honors the WebView's reduced-motion query.

## Mobile chapter presentation

The Logistics host injects `ChapterDrawer` into imported and rich provider EPUB
readers. Its native overlay retains the detail widget in place and never reserves
a sidebar column. Outside taps, chapter selection, Back, route changes and reader
retirement dismiss the drawer. The native overlay follows window resizing.
High Contrast / E Ink suppresses its opening slide and cancels active drawer
motion when the preference changes; dismissal is immediate. Native validation
of the chapter drawer on iOS and Android is still pending.

## Mobile EPUB spreads

`mobile/presentation.py` paginates the inert chapter into one or two CSS columns.
Wide landscape viewports (width >= 700 and height >= 480 logical pixels) use two
columns, as does an active vertical fold. The column stride includes the gutter;
turns and seeks snap to a whole spread, including an odd final page. Saved UTF-16
anchors retain their meaning across rotation, typography and fold changes.
Maximum reading width caps each text column, and the smaller physical half caps
both columns equally. Surplus width becomes an outer margin rather than stretching
one page or moving the gutter away from the crease.

The host binds `ChapterBridge.geometry_provider` for imported and rich provider
readers. `fold_layout.epub_geometry` queries the WebView's own reserved region and
normalizes the crease center and width to that view. Hinge updates call
`sync_epub_geometry` even without a viewport-size change; geometry changes reflow
without animation. UIKit reserved-region support supplies the existing platform
geometry. Platforms without that support use the viewport midpoint. The plain-text
fallback remains single-page.

`test_epub_dom.py` / `epub_index_dom.cjs` verify actual browser columns, crease
clearance, full-spread turns, right-page seeks, final-spread navigation, UTF-16
selection, motion suppression and anchor retention. `test_fold_layout.py` checks
view-local geometry delivery to imported and private bridges. Physical iOS/Android
posture and rendering validation remains pending.

## Mobile surface publication

Format controllers prepare their own EPUB/comic surfaces and retain source-specific
progress and metadata policy. Library and provider views publish through the
host's `mobile.reading.publication.ReadingPublication` coordinator for generation
validation, retirement and footer/chrome synchronization. Keep preparation inside its scope
so failed construction releases outgoing animation snapshots. Do not replace the
shared publication sequence with another format-specific container-clear path.
See [mobile publication ownership](../../../development/mobile-runtime.md#reader-publication-boundary)
for failure boundaries and focused/native verification.


## Shared appearance refreshes

The EPUB reader compares effective preferences, reading font and rendered colors
before responding to a shared styling notification. Unrelated UI/browser/code
changes leave the imported chapter intact. Automatic reading families still
inherit interface font changes, and slate/dark themes still adopt shared accent
tint changes. `test_books_reader.py` covers skipped imports, reading-size updates
and successive slate color notifications.

## Whole-book mobile progress

`features.books.locations.book_boundaries` supplies the resource-size weights
shared by desktop and mobile progress. This is an approximation that avoids
rendering every spine resource. Mobile PageFooter combines the chapter weight
with the current UTF-16 text offset; its normalized scrubber maps back to a
chapter and relative passage position. Imported and provider readers defer that
relative target until the selected chapter's text index is prepared, preserving
existing saved-position and private-session ownership.
