# Books mobile workflows

## Mobile development builds

The independent native app has private EPUB and PNG/JPEG CBZ/ZIP reading,
chapter/page progress and bookmarks. It has a smaller format/UI scope than this
desktop guide. See the [mobile guide](../../../../../docs/user_mobile/user_mobile.md)
for imports, limits and current validation status.

## Native mobile reading

Imported EPUBs support nested contents, archive-local chapter/section links and
**Find in chapter…** in the reader menu. Search ignores case and wraps within the
current chapter. Previous/Next and horizontal swipes turn discrete pages and continue into adjacent
chapters at the ends. EPUB text does not scroll vertically. External links and book scripts remain blocked.

Open the top-left hamburger for a nested **Chapters** sidebar. Expand or collapse
sections with the disclosure button, or tap a chapter title to read it. There is
no search field in this list. On wide panes the list stays beside the book; on
phones choosing a chapter returns to the page. Bookmarks remain below the list. Choosing an imported chapter or
bookmark returns directly to reading. The footer
shows the current chapter and percentage through its text. Page margins come
from **Appearance…**, without an extra frame narrowing the text. Chapter headings,
paragraphs and quotations use consistent spacing within the page.

Enable **Settings → EPUB → Justify text** or **Appearance… → Justify text** to
align paragraphs and lists to both edges. The same device preference applies to
imported and provider-backed rich EPUB readers and defaults to off. It is separate
from Markdown justification and does not change book files, headings, code blocks
or tables. The native plain-text fallback keeps its platform alignment.

Imported resume and bookmarks now store a chapter path and text offset. Reopening
or changing appearance restores that passage. Existing chapter-only bookmarks
remain available at chapter starts. Position saves follow page turns; a sudden process kill can lose the latest
unsaved movement.

On Android and iPad/iPhone, provider-backed EPUBs, including LocalCrypt, use the
same safe rich rendering, nested contents, internal links, discrete page turns and
highlighted chapter search as imported books. **Appearance…** offers the same fonts,
spacing, width, margins and themes described below. Changing appearance or leaving and
returning to the reader keeps the passage. Provider positions/bookmarks stay in
the session and clear on close; they are not saved as ordinary imported records.
Provider-backed books use the same nested chapter sidebar. **Find in chapter…**
is a separate reader action. A successful search returns to the passage; an
unsuccessful search keeps its feedback open.

Tap the fullscreen icon or choose **Fullscreen** in the reader menu to hide
navigation and reading controls. Pages continue to turn by horizontal swipe.
**Show reading controls** exits fullscreen. Changing the available space reflows
pages around the same text anchor.

Private EPUB rendering uses a nonpersistent iOS browser store or an Android view
with disk caching and browser storage disabled. Closing or suspending disposes the
view; HTML over 2 MiB is refused before the toolkit can create a disk-backed page.
Other backends use bounded native text passages.

Tap the **speaker** icon in the EPUB reader toolbar to open **Read aloud** (also
available in the reader actions menu). Playback controls float over the page
without resizing or reformatting it. The speed slider snaps in 25% steps from
**50%** to **200%**, with small gray limit labels and the current percentage above
the track. Choose speed and press **Play**. Choose your
installed offline voice in **Settings → Read aloud → Read-aloud voice**; the
voice picker is kept out of document views. Selected text
is read on its own; with no selection, reading starts at the current passage and
continues through this chapter. The current word is highlighted and brought into
view using system speech progress. Android voices that omit word progress use
estimated highlighting. Android initially selects the system's current voice
when it is installed and works offline. The same **Play/Pause** button switches to
pause while reading and back to play when paused. Pausing stops at the current
word; playing again continues from that word. Speed changes apply immediately
from the current word during playback, or on resume when paused. **Stop** ends
reading; pressing Play again starts at the top of the visible page unless text
is selected. Playback uses icon buttons with accessible names. The
back/forward **15** controls use the same circular-arrow design as desktop and
jump approximately 15 seconds within the current
passage, accounting for the selected speed. System speech has no recorded
timeline, so skips estimate distance at 180 words per minute at normal speed.
Skipping clears the previous spoken-word highlight before showing the new word,
including when paused. Skipping while paused keeps playback paused. Tapping outside the popup hides the controls
and keeps playback running, including automatic page turns within the chapter.
Tap the speaker again to reopen the same controls. Changing chapters,
leaving a private reader or closing its session stops
the engine and clears queued text. The app does not download voices or send text
to a speech service. If no offline voice is available, use the operating system's
speech settings to install one. Physical-device audio and accessibility ergonomics
still need a device pass.

Below Speed, **Timer** offers **Off** (the default), **15 min**, **30 min**,
**45 min**, and **1 hr**. The remaining time appears in bold beneath the timer
controls. The circular-arrow icon beside the duration is **Reset timer**.
**Time remaining** counts down only during playback;
pausing or stopping keeps the remaining budget for the next Play. **Reset timer**
restores the selected duration without changing whether speech is playing or
paused. Changing the duration also resets the budget. At zero, speech pauses at
the current word; Play resumes with a fresh full timer. Hiding the controls keeps
the timer active. The timer belongs to the open speech panel, is shared by mobile
EPUB and Markdown read-aloud, and clears when that panel is disposed.

In portrait and landscape, EPUB keeps Previous/Next and chapter progress in a
compact footer. On iOS the native top bar centers the book title, with the chapter
browser on the left and speech and Actions on the right. **Appearance…**, chapter
search and **Fullscreen** remain available in Actions. Comics use the same title
bar and keep their page scrubber; neighboring-comic buttons appear when supported
and available. Comics do not show EPUB chapter or read-aloud controls.

**Appearance…** now includes installed local font families, every whole font size
from 12–32, line spacing from 100–220%, maximum reading width from 480–1400 pixels
(or 0 for automatic), margins, and System/Light/Dark/Sepia/Slate themes.
System, Light and Dark use the app's matching surface and text colours across the
whole reading area, including page margins. Sepia and Slate retain their book colours.
On a narrow screen, reading width stays
inside the available pane. These settings are global mobile preferences, do not
rewrite books, and retain the current logical text anchor when layout changes.
The default theme is **system**, which follows the device's light/dark mode and
updates as that mode changes. Explicit Light/Dark/Sepia/Slate choices override it.
These text controls appear only for EPUBs. Comic appearance shows its page-layout
choice separately, and applying a comic layout does not rewrite EPUB preferences.

**Edit metadata…** also works on an ordinary imported EPUB copy. Saves preserve
other archive resources and leave the external import source unchanged. Failed
saves retain the form edits. The library recovers an interrupted checksum-record
publication when reopening the edited copy.

### Mobile fullscreen reading

On iPhone, iPad and Android, choose **Fullscreen** from an EPUB reader menu
to hide app navigation and system bars. Text retains its reading margins and safe
areas. **Show reading controls** remains available below the text so you can restore
Contents, Appearance, bookmarks and navigation without a gesture that interferes
with text selection or links. Imported and provider/private EPUBs support this mode;
private positions and bookmarks retain their existing session-only lifetime.

### Mobile EPUB speech and expanded appearance

EPUB reader menus now include **Read aloud…**, with installed offline voices,
speed, selected-passage playback, pause/resume and stop. Resume continues from the current word. Private-reader suspension stops speech and clears its queued text.
Appearance includes local font families, custom line spacing and maximum width,
and Sepia/Slate alongside existing themes. See the
[Books guide](reading.md#native-mobile-reading).

Imported catalogue search indexes all ordinary imports incrementally, persists a
disposable local cache, and shows 50 results per page. Comic edit forms offer
collection suggestions. Ordinary local and unlocked LocalCrypt folders have recursive comic
metadata batches through **Files → Actions → Edit comics in this folder…**. See the
[Comics guide](../../../comics/docs/user_mobile/reading.md#mobile-collection-search-and-folder-batches)
for scan limits, explicit-field saves and private-session cleanup.

### Lock-screen read-aloud

Started read-aloud uses system media controls on iOS and Android, with Play/Pause
and approximate backward/forward 15-second skips. With a timer selected, their
subtitle shows **Time remaining: MM:SS**, refreshed from the same countdown as
the floating panel. Pause freezes it; Reset timer and duration changes in the
panel update it immediately. Turning the timer Off removes the countdown.
Ordinary imported EPUBs, Markdown previews, public notes and documentation may
show their filename as the heading. Document passages never appear in the lock
screen, Control Center or Android media notifications. Private readers keep the
generic **Read aloud** heading and never show filenames or credential names.
Turning the timer Off leaves only the app name in the subtitle.
The operating system controls the exact lock-screen layout and refresh timing.
Playback and controls end when
the passage finishes, the document closes or its credentials are revoked. For
session-only credentials, background speech is disabled unless **Settings →
Session-only speech while locked** is enabled. The saved opt-in does not unlock
credentials or allow another chapter/file to be read while locked. See
[the speech setting](../../../../../docs/user_mobile/settings/settings.md#speech-while-locked).

EPUB page swipes work with reading controls visible or hidden. On iOS,
horizontal reader swipes take priority over navigation swipe back. Use Back
or the destination tabs to leave the reader.
