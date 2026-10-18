# Mobile navigation

## Home and document search

On iPhone Duo, pages retain their full available height when the system moves
the destination bar into a vertical rail. The rail uses the native side safe
area; bottom-bar clearance applies only to a horizontal destination bar.
When the Duo is partially open with a vertical fold, Home aligns its action and
Recent/Your spaces columns with the physical center seam, including when the
navigation rail makes the available content area asymmetric. Fully opening the
device restores the ordinary responsive layout.

Home shows **Your workspace**, with a **Continue** card for the selected document,
**New document** and **Open file…**. Recent lists up to ten other files; Folder Hub and Books & Comics remain available below. Wider windows put
Recent and Your spaces side by side. Continue restores the document's
Edit/Preview mode. Open file browses existing Local/LocalCrypt files and detects
the supported format when you open one.

When an unloaded credential ZIP is retained on disk, **Unlock** appears beside
**Your workspace**. Choose a credential and enter its ZIP password to unlock it
for this app session, then return to Home. Home does not list credential or remote
names in this button. Disabled Legacy credentials are excluded from the chooser;
if only Legacy is available and Show Legacy is off, the button stays hidden.
Passwords are never saved.

Documents puts **Open documents** first, with New document and Open file in a
compact toolbar. Open files are grouped by Text, Markdown, EPUB books and Comics;
empty groups are omitted. **Document card overview** switches between preview
cards and compact rows. Cards use bounded excerpts of ordinary text drafts;
private provider contents are never previewed here. Cards use one column on
phones, two in wider windows and three on large tablets. Closing an item retains
its stored file and uses the existing unsaved-change guard. Recent appears below
open documents and excludes files already open. A disk or cloud icon beside each
filename identifies its source; connection-backed files also show a locked or
unlocked padlock. Ordinary local files and files using saved credentials can remain
in Recent after closing or restarting. For a password-protected session-only
credential ZIP, the app saves open and recent entry lists in an AES-256 ZIP using
that credential ZIP's password. These entries appear only after you unlock the
matching credential; restoring the list does not download or open every file.
Session-only paths and filenames stay out of ordinary history and workspace files.
Passwords, document contents and unsaved edits are not saved in this list cache.
**Forget saved credentials** also deletes these encrypted lists across windows.


Editor status distinguishes **Unsaved changes · recovery copy kept** from
**Saved on this device**. A recovery copy protects your draft; it does not save
back to an imported original or upload to Remote. A detected external file
change remains visible and offers **Save a copy…**. Local/LocalCrypt provider
editors retain their own source-save and session-only status.

The ordinary text/Markdown editor offers **Find** beside Save and Preview.
Search is literal, wraps through the active document, and supports **Match case**,
**Replace** and **Replace all**. Replacement text is literal too. Search controls
belong to each editor, so switching documents keeps their separate queries and
drafts. **Done** hides the controls. Replacements update the draft and use the
same checkpoint and conflict-aware save behavior as typing; press Save to publish
them. Search does not include other files or the separate private reader editor.

## File and conversation drawers

Documents has a hamburger in its navigation bar. Opening it reveals a menu
with **Browse Local Files**, on-disk unlocked LocalCrypt locations, **Recent**
(up to ten eligible files), **Comics Library**, and **Shortcuts** for new text,
new Markdown and Folder Hub. Browse and library shortcuts open the existing file
browser in the main area. LocalCrypt browse labels show the remote name without
a transfer-status suffix. Recent can reopen a closed document. Session-only entries restore from their encrypted list cache after credential unlock. The menu's comics folders come from the same discovery as Home's
**Books & Comics**; both show folder names without full paths. Books & Comics
uses folder icons and opens each folder through the existing file browser.

The menu leaves a strip of the current page visible on compact screens. Tap the
hamburger again to return. Reduce Motion skips the animation. Browsing retains
independent storage, folder, search and history, without changing Folder Hub's
selection. Folder Hub has no hamburger; use its Browse Local/LocalCrypt/Remote
actions instead.

At window widths of 640 points/dp or more, including a sufficiently wide Duo
window, the open Documents menu occupies the left half and the current document stays on
the right. In Documents, **Split** appears in a wide window with an editable document and lets you choose a second open text or Markdown
document, including editable provider files. The first stays on the left and the
chosen document opens on the right. Opening the hamburger replaces the left
editor with the menu; closing it restores the pair. **Use one document** in the
Split picker clears the pair. Narrowing the window shows the current document
without closing either session or losing its draft. Books and comics keep their
own reader controls and immersive mode.

LM Chat is a full-screen destination. Its top-left hamburger opens the conversation
list; choosing a conversation restores its unsent draft and messages. On a wide
Duo/tablet window the list occupies the left half and the conversation remains on
the right. Close the menu to give messages the full width. Chat configuration and
app Settings open as full-screen pages with native Back navigation, rather than
bottom sheets. Settings first lists categories on phones; tapping one opens its
options with native Back navigation. At 640 points/dp of usable width, including
an unfolded Duo in landscape, categories remain on the left and options on the
right. Rotation keeps the selected category and current values. Opening these
screens does not send a model request.

## Related pages

- [Mobile panels](panels.md)
- [iPad windows](windows.md)
