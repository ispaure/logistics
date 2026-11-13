# Books mobile workflows

On Android, **Appearance → Volume buttons turn pages** enables volume down for
next page and volume up for previous page. It is off by default and saved
separately for books and comics. Tap **Apply and return** to save. Each press
turns one page; holding a button does not repeat. Volume control resumes outside
the reading view, including its Appearance screen. The setting also applies to
remote and encrypted readers.

## Book cover on iPhone Duo

In **Settings → Books & Comics**, turn on **Book cover on outer display** to try
showing an EPUB's cover on the outer screen while you read on the inner screen.
The switch is off by default and saves your choice. The experiment requires camera
permission. iOS shows the green camera indicator, and the app runs the camera
without showing a preview or saving footage. Keeping the camera and outer display
active can drain the battery noticeably faster. The feature excludes session-only
and protected documents. Whether iOS presents the cover with this camera setup
still needs verification on a physical Duo.

## Mobile development builds

The native app reads EPUBs and CBZ/ZIP comics with PNG/JPEG/static WebP pages.
It supports chapter/page progress and EPUB bookmarks, with a smaller format/UI
scope than the desktop reader. See the [mobile guide](../../../user_mobile/user_mobile.md)
for imports, limits and current validation status.

## Native mobile reading

Imported EPUBs support nested contents, archive-local chapter/section links and
**Find in chapter…** in the reader menu. Search ignores case and wraps within the
current chapter. Previous/Next and horizontal swipes turn discrete pages and continue into adjacent
chapters at the ends. EPUB text does not scroll vertically. A wide landscape reading area (at least 700 logical pixels wide and 480 high)
shows two equal-width pages. Narrow panes and portrait layouts show one page.
A reported active vertical crease also enables a spread: both text columns use
the width available on the smaller side, with their central gutter aligned to
the crease and its reserved region kept clear. Extra space remains as a blank
outer margin in the book's background color. Flat screens use the reading area's
midpoint. Previous/Next and swipes advance one spread; an odd last page leaves
the other half empty. The maximum reading width applies to each page, and
rotation or a crease change retains the current passage. Crease positioning
requires the platform to report a reserved fold region; otherwise the spread
uses the midpoint. Physical fold-posture validation is still pending. External links and book scripts remain blocked.

After a page turn, rotation keeps a passage near the middle of the displayed
page or spread visible. During read-aloud, including while paused, rotation
instead shows the page containing the highlighted word. Repeated rotations
retain that same text position even when page counts change.

The iOS app declares both portrait and both landscape orientations. Upside-down
portrait remains subject to device support: [Apple documents that iPhones without
a Home button do not support it](https://developer.apple.com/documentation/uikit/uiviewcontroller/supportedinterfaceorientations),
while iPads support all four orientations.

Open the top-left hamburger for a nested **Chapters** overlay. Expand or collapse
sections with the disclosure button, or tap a chapter title to read it. There is
no search field in this list. On iPhone, iPad and Android the list floats over the page without changing its
width or reflowing the text. Tap outside, press Back, or choose a chapter to close it. Bookmarks remain below the list. Choosing an imported chapter or
bookmark returns directly to reading. The footer
shows the whole-book percentage, **Page X of N**, then **Chapter X of Y** centered
below the progress bar in muted text matching the storage description.
Its slim slider jumps to a screen page when released; the arrows still turn
pages. Side margins come
from **Appearance…**, without an extra frame narrowing the text. The page has no extra
top or bottom padding; the header and progress controls provide the separation.
Chapter headings, paragraphs and quotations use consistent spacing within the page.

Enable **Settings → EPUB → Justify text** to
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
returning to the reader keeps the passage. Provider positions and bookmarks are kept separate from ordinary import records.
With an owning credential ZIP password, they can persist encrypted; passwordless
sessions keep them in RAM. Locking retires the active decrypted state. See
[private reading state](../../../development/reader-state.md).
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
without resizing or reformatting it. Tap the speaker again to hide the panel, or
tap outside it. Hiding the panel keeps playback active; tap the speaker to bring
its controls back. The speed slider snaps in 25% steps from
**50%** to **200%**, with small gray limit labels and the current percentage above
the track. Choose speed and press **Play**. Choose your
installed offline voice in **Settings → Read aloud → Read-aloud voice**; the
voice picker is kept out of document views. Selected text
is read on its own; with no selection, reading starts at the current passage and
continues through subsequent chapters to the end of the book. Selected text
stops at the selection's end. Chapter changes keep the same speech controls,
speed and remaining sleep-timer budget; Stop or closing the reader cancels
continuation. The current word is highlighted and brought into
view using system speech progress. Android voices that omit word progress use
estimated highlighting. Android initially selects the system's current voice
when it is installed and works offline. The same **Play/Pause** button switches to
pause while reading and back to play when paused. Pausing stops at the current
word; playing again continues from that word. Speed changes apply immediately
from the current word during playback, or on resume when paused. **Stop** ends
reading; pressing Play again starts at the top of the visible page unless text
is selected. Playback uses icon buttons with accessible names. The
back/forward **15** controls jump approximately 15 seconds at the selected speed.
For whole-book playback, any time left in the jump carries into the preceding
or following chapters. The jump passes over empty chapters and clamps to the
first or last spoken word. For selected text, the controls stay inside the
selection. Skips estimate distance at 180 words per minute at normal speed.
Skipping clears the previous spoken-word highlight before showing the new word,
including when paused. Skipping while paused keeps playback paused. Tapping outside the popup hides the controls
and keeps playback running, including automatic page turns within the chapter.
Tap the speaker again to reopen the same controls. Manually changing chapters,
leaving a private reader or closing its session stops
the engine and clears queued text. Settings → Read aloud loads installed voices
automatically when opened; Refresh voices retries discovery after changing system
voice data. On iOS, opening Read aloud also retries voice discovery once if the
speech engine fails to start or initially finds no voices. Reopening an unavailable
Read aloud panel retries again. If a saved voice is unavailable, playback uses the installed system
default. The saved preference can be selected again if that voice is reinstalled. The app does not download voices or send text
to a speech service. If no offline voice is available, use the operating system's
speech settings to install one. EPUB and Markdown read-aloud detect the passage’s
language offline and choose a matching installed voice. EPUB chapter/package
language declarations provide a fallback for short or ambiguous text. A saved
voice is preferred when it matches the detected language. If that language has
no installed voice, playback explains which language needs a voice. Detection
runs when starting a passage; it does not switch voices sentence by sentence.
Physical-device audio and accessibility ergonomics
still need a device pass.

EPUB and Markdown share punctuation handling: prose dashes separate words,
discretionary line-wrap hyphens are omitted from speech, and sentence endings
keep their closing quotes. Question marks, exclamation marks, periods and
ellipses remain in the speech text for the installed voice to interpret.
These adjustments preserve the document and its selection/highlight positions.

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

In portrait and landscape, EPUB keeps Previous/Next and whole-book progress in a
compact footer. The percentage comes from the current text position, so the same
saved position in the same EPUB gives the same percentage on different screens.
The reader opens the current chapter while it counts the book's text in the
background. **Page X of N** and the scrubber use screen pages for the current
layout. Two-page spreads show a page range. The footer shows **Counting pages…**
and disables the scrubber until the screen-page count finishes. Font and
viewport changes recount screen pages while keeping the text position. Counts
are held for the current reader session. On iOS the native top bar centers the book title, with the chapter
browser on the left and speech and Actions on the right. **Appearance…**, chapter
search and **Fullscreen** remain available in Actions. Comics use the same title
bar and keep their page scrubber; neighboring-comic buttons appear when supported
and available. Comics do not show EPUB chapter or read-aloud controls.

**Settings → EPUB** includes installed local font families, every whole font size
from 12–32, line spacing from 100–220%, maximum reading width from 480–1400 pixels
(or 0 for automatic), margins, and System/Light/Dark/Sepia/Slate themes.
System, Light and Dark use the app's matching window background and text colours
across the whole reading area, including page margins, so text blends into the
surrounding view. Sepia and Slate retain their book colours.
On a narrow screen, reading width stays
inside the available pane. These settings are global mobile preferences, do not
rewrite books, and retain the current logical text anchor when layout changes.
Changes save as you edit. The reset button beside the font-size picker restores
the default size of 16. When you open this page from the book’s **Appearance…**
menu, Back returns to the same passage.
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
private bookmarks use credential-password encryption when available, with a RAM-only fallback for passwordless sessions. The main reader's **Back arrow**
closes the reader and returns to its originating folder or screen. Android Back
does the same after dismissing chapter/search panels; secondary screens retain
Back to reading. Unsaved metadata edits prompt before close. Imported reading
progress stays saved. Provider EPUB passage positions follow the credential-bound persistence policy
above; closing does not turn them into ordinary import history.

### Mobile EPUB speech and expanded appearance

EPUB reader menus now include **Read aloud…**, with installed offline voices,
speed, selected-passage playback, pause/resume and stop. Resume continues from the current word. Private-reader suspension stops speech and clears its queued text.
Appearance includes local font families, custom line spacing and maximum width,
and Sepia/Slate alongside existing themes. See the
[Books guide](reading.md#native-mobile-reading).

Ordinary imports have an incremental disposable metadata cache; the Books &
Comics screen itself lists configured folders, without imported-results search
or paging. Comic edit forms offer collection suggestions. Ordinary local and unlocked LocalCrypt folders have recursive comic
metadata batches through **Files → Actions → Edit comics in this folder…**. See the
[Comics guide](../../comics/user_mobile/reading.md#mobile-collection-search-and-folder-batches)
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
The system skip controls follow the same chapter boundaries as the panel.
While a private book is locked with background speech enabled, playback and
skips can use the chapter already loaded. At the end of that chapter, speech
waits for you to unlock, return to the book and tap **Play**. Unlock and
return to the book before requesting a skip into another private chapter.
Turning the timer Off leaves only the app name in the subtitle.
The operating system controls the exact lock-screen layout and refresh timing.
Playback and controls end when
the passage finishes, the document closes or its credentials are revoked. For
session-only credentials, background speech is disabled unless **Settings →
Privacy & Security → Session-only speech while locked** is enabled. The saved opt-in does not unlock
credentials or allow another chapter/file to be read while locked. See
[the speech setting](../../../user_mobile/settings/settings.md#speech-while-locked).

EPUB page swipes work with reading controls visible or hidden. On iOS,
horizontal reader swipes take priority over navigation swipe back. Use Back
or the destination tabs to leave the reader.

## Returning after sleep

If Android releases reader memory while the device sleeps, the visible imported
comic or EPUB reloads at its saved page or passage when you return. Reading mode
or visible controls are preserved. Closed documents and readers on other screens
stay closed or inactive. Password-protected documents retain their usual unlock
requirements; session-only content is revealed only after its session password.

## Page-turn motion

Page changes use a short slide. **High Contrast / E Ink** disables page-turn
motion and the chapter-overlay opening slide on mobile. The chapter overlay
closes immediately. System reduced-motion preferences are respected.
EPUB slides apply within a chapter and when changing chapters. Seeking within a
chapter, resizing the reader and restoring a saved position do not animate.
