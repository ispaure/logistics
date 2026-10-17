# Reading and editing on mobile

## Reading and editing

Open EPUB and comic sessions now give content the main area, with compact page
navigation and a format-specific Actions menu. EPUB offers contents, bookmarks,
text appearance, chapter search and read-aloud; comics offer page navigation,
page layout, fit and neighboring-comic actions where supported. EPUB pages turn using Previous/Next or horizontal swipes, with no vertical
scrolling. Its hamburger opens a nested chapter sidebar without a search field.
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

Markdown files open in preview. Tap **Edit Markdown** to edit in a single
**Formatted** surface on phones and tablets. **Source** switches to the exact
Markdown text; it never adds a second pane. New Markdown documents start editing.
Formatted mode offers Bold, Italic, Undo and Redo icon buttons matching desktop. **Format** adds
strikeout, heading levels, lists, quotes, inline/code blocks, links and table
insertion or row/column changes. Table cells and code blocks are editable. YAML properties, reference links, wiki
aliases and unsupported syntax remain available through Source. Untouched blocks
retain their original Markdown; editing a block can normalize its spelling.
**Preview** shows the current draft, and saving remains explicit. Provider-backed
Markdown uses the same single-surface editor and retains its existing save rules.
See [Text and Markdown](documents.md#text-and-markdown) for saving and private drafts.

## Markdown read-aloud

Tap the **speaker** icon in the Markdown preview or vault reader toolbar to open
**Read aloud**. Choose an installed
offline system voice and speed, then **Play**. Selected text is read when present;
otherwise the rendered note is read from the beginning. **Pause** and **Resume**
repeat the current sentence; **Stop** ends playback and **Close** hides controls.
Playback has accessible icons, including back/forward **15** controls. These
estimate 15 seconds from word count and the chosen speed; skipping while paused
keeps it paused. Speech stops when leaving the viewer, switching notes, closing the document or
locking private content. Install an offline voice in system settings if needed.
Private text stays in memory and is passed only to the system speech engine.

## PDF documents

Open local, remote or LocalCrypt PDFs directly in a read-only session. Enter a
page number and tap Go, or swipe up/down to turn pages. See the
[mobile PDF guide](../../../Python/features/pdf/docs/user_mobile/user_mobile.md)
for limits and private-session behavior.
