# Books mobile workflows

## Mobile development builds

The independent native app has private EPUB and PNG/JPEG CBZ/ZIP reading,
chapter/page progress and bookmarks. It has a smaller format/UI scope than this
desktop guide. See the [mobile guide](../../../../../docs/user_mobile/user_mobile.md)
for imports, limits and current validation status.

## Native mobile reading

Imported EPUBs support nested contents, archive-local chapter/section links and
**Find in chapter…** in the reader menu. Search ignores case and wraps within the
current chapter. Previous/Next move by a visible screen and continue into adjacent
chapters at the ends. External links and book scripts remain blocked.

Imported resume and bookmarks now store a chapter path and text offset. Reopening
or changing appearance restores that passage. Existing chapter-only bookmarks
remain available at chapter starts. Position saves are debounced while scrolling;
a sudden process kill can lose the most recent unsaved scroll movement.

On Android and iPad/iPhone, provider-backed EPUBs, including LocalCrypt, use the
same safe rich rendering, nested contents, internal links, screen-sized turns and
highlighted chapter search as imported books. **Appearance…** offers the same fonts,
spacing, width, margins and themes described below. Changing appearance or leaving and
returning to the reader keeps the passage. Provider positions/bookmarks stay in
the session and clear on close; they are not saved as ordinary imported records.

Private EPUB rendering uses a nonpersistent iOS browser store or an Android view
with disk caching and browser storage disabled. Closing or suspending disposes the
view; HTML over 2 MiB is refused before the toolkit can create a disk-backed page.
Other backends use bounded native text passages.

Choose **Read aloud…** from an EPUB reader menu. Select an installed offline voice
(the label includes its language), choose speed, and press **Play**. Selected text
is read on its own; with no selection, reading starts at the current passage and
continues through this chapter. The current sentence or bounded passage is
highlighted and brought into view. **Pause** stops at the current utterance;
**Resume** repeats that sentence/passage. **Stop** ends reading. Closing the speech
panel, changing chapters, leaving a private reader or closing its session stops
the engine and clears queued text. The app does not download voices or send text
to a speech service. If no offline voice is available, use the operating system's
speech settings to install one. Physical-device audio and accessibility ergonomics
still need a device pass.

**Appearance…** now includes installed local font families, every whole font size
from 12–32, line spacing from 100–220%, maximum reading width from 480–1400 pixels
(or 0 for automatic), margins, and System/Light/Dark/Sepia/Slate themes. The explicit
theme colours are shared with desktop. On a narrow screen, reading width stays
inside the available pane. These settings are global mobile preferences, do not
rewrite books, and retain the current logical text anchor when layout changes.
These text controls appear only for EPUBs. Comic appearance shows its page-layout
choice separately, and applying a comic layout does not rewrite EPUB preferences.

**Edit metadata…** also works on an ordinary imported EPUB copy. Saves preserve
other archive resources and leave the external import source unchanged. Failed
saves retain the form edits. The library recovers an interrupted checksum-record
publication when reopening the edited copy.

### Mobile fullscreen reading

On iPhone, iPad and Android, choose **Reading mode** from an EPUB reader menu
to hide app navigation and system bars. Text retains its reading margins and safe
areas. **Show reading controls** remains available below the text so you can restore
Contents, Appearance, bookmarks and navigation without a gesture that interferes
with text selection or links. Imported and provider/private EPUBs support this mode;
private positions and bookmarks retain their existing session-only lifetime.

### Mobile EPUB speech and expanded appearance

EPUB reader menus now include **Read aloud…**, with installed offline voices,
speed, selected-passage playback, pause/resume and stop. Resume repeats the current
sentence/passage. Private-reader suspension stops speech and clears its queued text.
Appearance includes local font families, custom line spacing and maximum width,
and Sepia/Slate alongside existing themes. See the
[Books guide](reading.md#native-mobile-reading).

Imported catalogue search indexes all ordinary imports incrementally, persists a
disposable local cache, and shows 50 results per page. Comic edit forms offer
collection suggestions. Ordinary local and unlocked LocalCrypt folders have recursive comic
metadata batches through **Files → Actions → Edit comics in this folder…**. See the
[Comics guide](../../../comics/docs/user_mobile/reading.md#mobile-collection-search-and-folder-batches)
for scan limits, explicit-field saves and private-session cleanup.
