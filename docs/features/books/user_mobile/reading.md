# Books mobile workflows

On Android, enable **Appearance → Volume buttons turn pages**, then tap **Apply and return**. Volume down advances and volume up goes back in the reader. This off-by-default setting is separate for books and comics.

## Book cover on iPhone Duo

Enable **Settings → Books & Comics → Book cover on outer display** to try displaying the EPUB cover while reading on the inner screen. This experimental setting requires camera permission, displays the green indicator and can drain the battery faster. Footage is neither previewed nor saved. Protected and session-only documents are excluded. Physical Duo display behavior is still unverified.

## Mobile development builds

See the [mobile guide](../../../user_mobile/user_mobile.md) for supported storage and validation, or [book imports](library.md) for limits.

## Native mobile reading

Use the chapter button to open nested contents and bookmarks. Tap a title to jump or a chevron to expand. **Find in chapter…** searches without case and wraps. The arrows and horizontal swipes turn pages across chapter boundaries. Drag and release the footer slider once screen-page counting finishes.

Wide landscape panes and a reported vertical fold show spreads. The fold stays clear between equal text columns. Resizing or changing appearance keeps the current passage or the highlighted speech word. Bookmarks retain text offsets, with older chapter-only bookmarks opening at the chapter start.

Imported, remote and LocalCrypt books offer rich pages, internal links and chapter search. Book scripts and external resources are blocked. Provider positions use encrypted checkpoints when a credential ZIP password is available. Passwordless private state stays in memory. Locking retires decrypted state. See [private reading state](../../../development/architecture/reader-state.md).

**Edit metadata…** updates the ordinary imported copy. A failed save keeps form edits, while reopening can recover an interrupted archive/checksum publication.

### Mobile fullscreen reading

Choose **Fullscreen** to hide navigation and system bars. Swipe to turn pages and choose **Show reading controls** to exit. Use Back to return to the originating folder or screen. On iOS, the page swipe takes priority over swipe-back.

### Mobile EPUB speech and expanded appearance

Open the speaker or **Read aloud**. Select text for passage-only playback, or start at the current passage and continue through later chapters. Speed ranges from 50% to 200%. Play/Pause resumes at the highlighted word. Skips go about 15 seconds and carry across chapters during whole-book playback. Manual chapter changes or private-reader suspension stop playback. Hiding the panel keeps it playing.

Choose an installed offline voice under **Settings → Read aloud → Read-aloud voice**. Detection chooses a matching language locally, using EPUB language metadata when needed. Use **Refresh voices** after installing a voice, or reopen the speech controls if the engine fails to start.

**Timer** offers Off and durations from 15 minutes to one hour. Its budget runs only during playback. **Reset timer** restores the selected duration. At zero, speech pauses. Play starts a fresh timer.

Use **Appearance…** or **Settings → EPUB** for local fonts, sizes 12–32, spacing, width, margins, justification and System/Light/Dark/Sepia/Slate themes. These settings are device-wide and save immediately. Back returns to the same passage. For comic layouts and editing, see [Comics](../../comics/user_mobile/reading.md#mobile-collection-search-and-folder-batches).

### Lock-screen read-aloud

System controls show Play/Pause, 15-second skips and any active timer. Private controls show **Read aloud** without filename, credentials or passage text. Enable **Settings → Privacy & Security → Session-only speech while locked** for background speech with session-only credentials. While locked, private playback can use only the loaded chapter. Unlock, return to the book and press **Play** to continue. Revoking credentials ends playback. See [the speech setting](../../../user_mobile/settings/settings.md#speech-while-locked).

## Returning after sleep

If Android releases memory, the active imported reader reloads at its saved passage with its previous control visibility. Session-only content requires its usual unlock.

## Page-turn motion

**High Contrast / E Ink** and system reduced motion disable page-turn slides.
