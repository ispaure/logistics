# Reading and editing on mobile

## Reading and editing

EPUB, PDF and CBZ/ZIP comic files open from both **Local** and unlocked
**LocalCrypt**, including the Workspaces browser and document file drawer.
Choose the file directly; no format-specific connection setup is needed.
Local files can be opened immediately after launching the app. LocalCrypt uses
the unlocked connection to read its encrypted copy, keeping decoded content in
memory. A failed open keeps the file drawer available and displays the error.

Open EPUB and comic sessions now give content the main area, with compact page
navigation and a format-specific Actions menu. EPUB offers contents, bookmarks,
text appearance, chapter search and read-aloud; comics offer page navigation,
page layout, fit and neighboring-comic actions where supported. EPUB pages turn using Previous/Next or horizontal swipes, with no vertical
scrolling. Its hamburger opens a nested chapter sidebar without a search field.
EPUB keeps Previous/Next and chapter progress in a compact footer. Speech and
Actions stay above the content. On iOS, readers and editors share the native
title bar: Back and the relevant browser are on the left, a centered document
title is in the middle, and supported actions are on the right. Long names
shorten in the middle. Appearance and fullscreen are in Actions.

Document **•••** menus group reading, appearance, file, navigation and close/delete
options in the same order across formats. **Show in folder** is available for
documents with a browsable source, including text, Markdown, PDF, images, EPUB
and comics. It reveals the file in Workspaces and returns to the appropriate
Local, Cloud or Home Server tab when you go back through its folders. Imported
books without a retained original location reveal their stored library copy.
**Open beside another document** appears only when the current layout is wide
enough and the document supports paired panes; it hides again on narrow layouts.

Fullscreen hides navigation and reading controls and keeps a visible
**Show reading controls** button. Comics open with controls hidden and zero page margins; tap the page to
show or hide reading controls. Native navigation bars hide with comic controls
and return when controls are shown or when leaving the reader. EPUB appearance offers supported font sizes, margins and system/light/dark
colors without changing the current chapter. Progress remains chapter/page based.
Fit comic pages remain centered after leaving and reopening a reader or repeatedly
showing and hiding controls; zoomed pages retain bounded pan and zoom behavior.
Fullscreen reclaims the navigation area on both platforms, including Android's
title bar. Transfer banners appear with reading controls and stay hidden during
immersive comic reading; this does not pause transfers in the background.

See [Comic gestures on mobile](../../../Python/features/comics/docs/user_mobile/gestures.md)
for magnification, pinch zoom, panning and swipe navigation.

Markdown files open in preview. Tap the top **pencil** icon (**Edit Markdown**) to edit in a single
**Formatted** surface on phones and tablets. **Source** switches to the exact
Markdown text; it never adds a second pane. New Markdown documents start editing.
Formatted mode offers Bold, Italic, Undo and Redo icon buttons matching desktop. **Format** adds
strikeout, heading levels, lists, quotes, inline/code blocks, links and table
insertion or row/column changes. Table cells and code blocks are editable. YAML properties, reference links, wiki
aliases and unsupported syntax remain available through Source. Untouched blocks
retain their original Markdown; editing a block can normalize its spelling.
The top **page** icon (**View document** or **View Markdown**) shows the current
draft. **Save** appears only while there are actual unsaved text changes and
disappears after saving or reverting; Save As and export remain explicit copying
actions. Markdown reading uses a single top toolbar, including its file drawer
and speech control, without an edit/save footer. On iOS the buttons share the
native title bar; Android uses one compact row. Provider-backed
Markdown uses the same single-surface editor and retains its existing save rules.
On iOS, Markdown's **•••** menu includes **Read aloud…**, keeping room for the
title beside the pencil. During editing, **Save** takes the primary action slot
when the buffer changes; **View document** remains in **•••**.
Text and Markdown editors on iOS keep the filename in the centered title rather
than repeating an editable name field below it. Use **Actions → Rename document…**
for managed documents. Notes Library and documentation use the same title bar;
previous/next history and parent-page actions are in their **•••** menus.
See [Text and Markdown](documents.md#text-and-markdown) for saving and private drafts.

## Markdown read-aloud

Tap the **speaker** icon in the Markdown preview or vault reader toolbar to open
**Read aloud**. Choose a speed, then **Play**. The controls float over the page without changing its
layout. Choose the offline system voice in **Settings → Read aloud → Read-aloud
voice**, using **Load installed voices** to list available voices. Selected text is read when present;
otherwise the rendered note is read from the beginning. **Pause** and **Resume**
repeat the current sentence; **Stop** ends playback and **Close** hides controls.
The current word is highlighted and brought into view on iOS and Android.
Highlight timing is estimated for Android voices that do not report word progress.
Playback has accessible icons, including back/forward **15** controls. These
estimate 15 seconds from word count and the chosen speed; skipping while paused
keeps it paused. Speech stops when leaving the viewer, switching notes, closing the document or
locking private content. Install an offline voice in system settings if needed.
Private text stays in memory and is passed only to the system speech engine.

If the Android voice list is empty, select a text-to-speech engine in phone
settings and install offline voice data for your language, then close and reopen
Read aloud. On Samsung phones, use **Settings → General management → Text-to-speech
→ gear beside Preferred engine → Install voice data**. Test the voice with
**Play** on that settings screen. See [Samsung's voice setup guide](https://www.samsung.com/us/support/answer/ANS10003701/).

## PDF documents

Open local, remote or LocalCrypt PDFs directly in a read-only session. Enter a
page number and tap Go, or swipe up/down to turn pages. See the
[mobile PDF guide](../../../Python/features/pdf/docs/user_mobile/user_mobile.md)
for limits and private-session behavior.
