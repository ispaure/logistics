# Mobile navigation

Commands such as **Open file**, **New document**, and **Set up chat** have neutral
outlined buttons. Icon commands also have visible
boundaries. Highlighted tabs and choices indicate the current selection; ordinary
commands do not stay highlighted after use. Folder names within browser rows keep
their row presentation, while chat Send/Stop keeps its distinct composer control.
Settings uses unboxed category and action rows, with gray descriptions separating
explanatory text from commands and native preference controls.

## iOS toolbars and iPhone Duo

On iOS, related screen actions share the system's glass background. Navigation
and completion actions stay distinct: Close or Back comes first, followed by a
primary action such as Save and then the remaining tools. On iPhone Duo, UIKit
moves eligible actions to the side on the outer display and inner landscape;
inner portrait uses horizontal bars. More actions join the system overflow menu
when a vertical bar is preferred. Search fields, file-row menus, reading progress,
playback and message composition remain with the content they affect.

## Opening documents

Opening text, Markdown, PDF, EPUB or comic documents keeps the current tab selected
on iOS and Android. Home opens a document above Home; Workspaces opens it above
the current folder. Back returns through document detail screens to that retained
origin, preserving its folder, search, selection and scroll state. Open sessions
and unsaved drafts remain available in Documents. Choosing **All documents**
explicitly switches to the Documents list.

## Android Back

The Android Back button and back gesture dismiss the current temporary surface
before leaving its screen. This includes a compact file/conversation drawer,
editor Find controls, PDF pages/search, book chapters, and fullscreen reading.
Back hides floating read-aloud controls while allowing playback to continue.
Android handles keyboard, native dialog and popup-menu dismissal itself.

In a file browser, Back clears an active search, closes its search controls,
then returns through visited folders. Opening a folder directly without history
falls back to its parent. The folder header's **Parent folder** arrow always
goes up one level; it can differ from Back after visiting several folders or
storage sources. Documentation and Notes Library follow their page/note history
before returning to the screen that opened them.

Reader tools, Settings categories, connection forms and transfer pages each
have their own return step. Leaving a transfer comparison cancels that review;
leaving an active transfer's details lets the transfer continue. Returning from
a main document with **× (Close document)** closes its session and returns to
the previous screen. Editors use the same Close control: unsaved changes offer
**Save**, **Quit without saving**, or **Cancel**. Failed saves
retain the edits. Secondary document panels keep their usual Back step.

Each bottom tab or rail destination retains its own place. Back follows the
current destination's screens. Opening a file from Workspaces keeps that tab selected; after leaving the file,
Back returns to the same folder. Ordinary
tab taps preserve each tab's place without creating these action return steps.
At a destination's root, Back returns to **Home**. From Home's root,
Android handles leaving the app. Switching tabs does not create a trail of tab
selections to undo. Wide companion sidebars stay in place while Back leaves the
active detail; compact drawers close first.

## Home and document search

In the file browser, Search checks filenames in the current folder and its
subfolders, ignoring case. Separate words all have to appear, in any order:
`end eternity` finds `The End of Eternityla.epub`. Double quotes keep words
adjacent and ordered: `"end eternity"` does not match that filename, but
`"end of eternity"` does. Within quotes, spaces, underscores and hyphens are
equivalent separators, as on desktop.

Opening Search prepares or refreshes an on-device database for ordinary local
folders in the background. Later queries reuse the saved index, including after
restarting the app. Reopen Search or refresh the folder to check for added or
renamed files. The first search in a large folder may take longer while the index
is built. Private, session-only and virtual sources use background scans without
saving their names to this database. Search covers names, not file contents.

On iPhone Duo, pages retain their full available height when the system moves
the destination bar into a vertical rail. The rail uses the native side safe
area; bottom-bar clearance applies only to a horizontal destination bar.
In landscape, Home and the Documents list use two independently scrolling
sections when there is enough room. Home puts file actions on the left, with
its short Recent list on the right. Documents puts search and All open on the
left, with Recent and Saved documents on the right. On Duo, both fully open and
partially open landscape layouts align these sections to the physical crease,
including when the navigation rail makes the usable area asymmetric. Cards,
filenames and buttons stay within their section. Returning to a narrow portrait
layout stacks the same controls into one scrolling page.

Home shows **Your workspace**, **Open file…**, **New document**, and up to five
recent files. **See all in Documents** opens the full document workspace. Tapping
an already open recent file restores its existing draft and Edit/Preview mode.
Open file browses existing Local/LocalCrypt files and detects the supported format
when you open one. Active transfer and recovery notices remain on Home.

When an unloaded credential ZIP is retained on disk, a bordered lock icon button
(**Unlock credentials**) appears beside **Your workspace**. Choose a credential and enter its ZIP password to unlock it
for this app session, then return to Home. Home does not list credential or remote
names in this button. Disabled Legacy credentials are excluded from the chooser;
if only Legacy is available and Show Legacy is off, the button stays hidden.
Passwords are never saved.

Documents shows **Search documents**, **All open**, **Recent**, **Saved documents**,
and **Open Books & Comics library**. All open lists every visible open
document, with the active one first and a Close button beside each. Recent shows
closed entries from the ten-file history; open entries stay in All open. Other
saved text and Markdown files appear in Saved documents without repeating files
already listed above. Search filters all three sections by filename, ignoring
case. Clearing search restores the lists. Closing keeps saved files and retains
the existing unsaved-change choices. Empty sections show plain messages, such as
**No open documents**, outside the rounded document groups.

**Currently open** appears as plain status text beneath recent filenames for documents
still open in the workspace. Select the filename to return to that document. **Unsaved changes** and
**Draft** mark pending edits; **Recovered draft** identifies edits available from
a recovery copy. These badges do not mean changes have been saved back to the
source. Saving clears the draft badges. Recent always uses compact rows without
text-preview cards. A disk or cloud icon beside each
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

Confirmation and information alerts dim the screen behind them while waiting
for your response. Android requests a 50% background dim; iOS uses the system
alert dimming. Dismissing the alert restores the screen.

## File and conversation drawers

Documents has a hamburger in its navigation bar. Opening it reveals a menu
with **Browse Local Files**, on-disk unlocked LocalCrypt locations, **Recent**
(up to ten eligible files), **Comics Library**, and **Shortcuts** for new text,
new Markdown and Workspaces. Browse and library shortcuts open the existing file
browser in the main area. LocalCrypt browse labels show the remote name without
a transfer-status suffix. Recent can reopen a closed document. Session-only entries restore from their encrypted list cache after credential unlock. The menu's comics folders come from the same discovery as Home's
**Books & Comics**; both show folder names without full paths. Books & Comics
uses folder icons and opens each folder through the existing file browser.

The menu leaves a strip of the current page visible on compact screens. Tap the
hamburger again to return. Reduce Motion skips the animation. Browsing retains
independent storage, folder, search and history, without changing Workspaces's
selection. Workspaces has no hamburger; use its Browse Local/LocalCrypt/Remote
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

## Browsing folders on iOS

In the Workspaces file browser, the native Back button and swipe-back gesture
move to the parent folder. At the storage root, Back returns to the Workspaces
overview. The browser omits its separate Up button on iOS. The folder name appears
once in the native title bar; the row below keeps storage identity and actions. Opening a pinned or
deep folder includes its ancestors in this navigation stack.
Home's **Open file…** browser uses the same parent-folder Back behavior. At its
storage root, Back returns to the screen that opened the picker. **Cancel**
returns there directly from any folder, keeping the original reader and draft.


A reader's **Show in folder** action switches to Workspaces, opens its containing
folder and selects the file. Back then follows parent folders; switching to the
reader's original tab returns to that reader. Back inside the reader still
returns to the screen from which the file was opened.

## Related pages

- [Mobile panels](panels.md)
- [iPad windows](windows.md)
