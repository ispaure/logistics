# Documents and readers

Open documents show a storage row beneath their title, using the browser's
storage icons and caption style. It identifies on-device/Cloud/Home Server,
LocalCrypt and unlocked/session-only state where applicable, and includes
**(Read-Only)** for read-only sessions. Connected Home Server locations offer
the same supported viewers as Cloud and keep documents read-only. Images open
as documents with previous/next image controls for the same folder.


Use the document workspace to return to open text, Markdown, books, comics and
conversations. Switching to another part of the app keeps these sessions available.
Tap **Documents** while that tab is already selected to return to the Documents
list without closing the current document. Switching to Documents from another
tab resumes any document already displayed within Documents; otherwise it shows
the list. Tap Documents again to see the list.

Home provides Open/New actions and five recent files. **See all in Documents**
opens Documents. **Libraries** is first and selected by default at app startup.
Beside it, the **heart** opens your favourite files. **Open**, **Recent** and
**Saved** follow. Each collection displays one list. Open puts the active document first and provides close controls;
closing a view keeps its saved file. Recent lists closed history entries. Saved
lists other saved text, Markdown and notebook documents. Libraries displays
discovered Notes libraries followed by configured Comics libraries, under
**Notes** and **Comics** headings. Tap a library directly to open it.

The upper-right **Search documents** magnifier beside Open and New opens a dedicated
filename search. It searches filenames recursively through Local,
Shared Files, Received Files and unlocked LocalCrypt storage, including files and folders
you have never opened. Results use compact filename rows with **…** actions;
**Show in folder** reveals the item in the file browser. It does not search file contents or online remotes.
While text is entered, results replace the collection buttons and lists.
Tap the upper-left **×** to return to the previous collection. Android Back also
exits search when the Documents overview is visible. Locked LocalCrypt
filenames remain hidden until you unlock their credentials. Unavailable
locations are reported rather than treated as an empty successful search.

Home, Workspaces and Documents share an **Unlock LocalCrypt** action whenever
retained credentials are available to unlock. Android places it at the right of
each overview's action row. iOS uses the native trailing actions, including
Duo's side bar on its folded and unfolded displays. UIKit chooses the bar's
edge after rotation. Unlocking returns to
the overview where you started. Documents also provides Open and New actions;
its overview has no collapsible hamburger menu.
When a vertical action bar has too little space, **Document actions** (**…**)
contains Open, New and Search while Unlock remains directly available.

In **New document**, enter a name and choose Plain text, Markdown or Notebook.
Tap **Choose location** to leave the keyboard and open the folder browser. Select
a folder in **Local**, **Shared Files**, **Received Files** or an unlocked **Encrypted Copy**
location. Changing the file type updates a matching document extension; a name
without an extension receives the selected one. Tap **Create document** to create
and open the file. On a narrow screen, **Back to name** keeps your chosen folder
while you edit the name or type. On a tablet or unfolded Duo with enough room,
the name stays on the left and the folder browser opens on the right. You can
edit either pane. Folding or rotating keeps the draft and selected folder.
The folder arrow navigates within the browser. Android Back dismisses folder
entry or search and retraces folder navigation first. At the root it returns
to naming on a narrow screen or exits when both steps are visible. **Cancel**
returns directly to the screen where you started. The file is
created in that folder and appears when you browse it from Shared Files. **Save**
writes edits back to the same file. LocalCrypt files stay encrypted on disk;
cloud locations are read-only and receive changes through reviewed **Push**.
New documents do not use the private saved-document store. Existing saved
documents remain available in Documents.

The New Document folder browser starts at **Shared Files**. Choose **Local**
or **Received Files** to browse those collections. Up returns to **Shared Files**
from either collection. The Move picker uses the same location names.
To make a subfolder, tap **New folder**, enter its name, then tap **Create folder**. The browser selects the new folder.
Cancelling the folder entry keeps the current location and your filename.
On Android this root is a list of locations;
the form prompts you to choose a folder and keeps **Create document** disabled there. Errors
appear as messages beneath the destination, with no extra editable field.
Correct the name or location and try again. Only existing LocalCrypt copies and
linked pulled folders appear; loading an encrypted remote alone adds no destination.
For a notebook, choose **Notebook (.rmdoc)** and a Local or unlocked LocalCrypt folder;
see [Notebooks on mobile](../../features/notebooks/user_mobile/user_mobile.md).

After **Create document** opens your new file, **×** closes it and returns to the
screen where you opened New document. It does not reopen the completed creation
form. A notebook's **×** returns to the Home overview. Unsaved edits still offer
Save, Quit without saving and Cancel.

In a book, comic or provider-backed document reader, open the **…** actions menu
and choose **All documents** to return to the Documents list without closing the
document. Opening a document from Home or Workspaces keeps that tab selected.
iOS navigation Back and Android system Back return to the retained opening screen
without closing the session. Android may first dismiss reading controls or
fullscreen mode.
While a file downloads or prepares to open from Home, Documents or Workspaces,
a separate panel shows its file icon, name and loading bar.
Measured full-file reads show **Reading N%** when the size is known, or
**Reading file…** when it is not. The bar switches to **Preparing document…**
while decoding and the first page finish. Opening paths that read selected
ranges, including PDFs, keep an indeterminate bar. The reader replaces the panel
when ready. Back returns to the opening screen, including when used
before loading finishes. Failed opens return to that screen too.
On iOS, the top navigation bar shows the opened document's filename with its
extension, without the folder path, including files opened from local, remote
and encrypted storage. Fullscreen reading hides the bar
until you show the reading controls again.

## Text and Markdown

Markdown files open in preview. **Edit Markdown** enters a single formatted
editing surface; **Source** shows the exact Markdown instead. Phones and tablets
use the same mode switch, without a second preview pane. **Preview** returns to
reading the current draft. New Markdown documents start editing. Preview and
formatted editing have a 1 MiB source limit; larger documents use Source.
See [Reading and editing](reading-and-editing.md) for supported formatting.

On Android 12 and newer, Markdown preview and formatted editing use the native
app font, including device font customizations when Android exposes the font.
Code remains monospace. Older Android versions use the platform font fallback.

Text and source files have logical line numbers, monospace text and syntax colours.
Automatic detects the filename, or choose a language from the selector. Wrapped
continuations keep the same logical line number. Common source/configuration
files, including Python, JSON, YAML, shell and JavaScript, can be opened and saved
through the file picker. Highlighting pauses above 128 Ki characters while text
editing and line numbers remain available. The mobile editor retains native
keyboard, selection and undo; desktop folding and multiple cursors are not
provided by this control.

Local/private Markdown uses the same Formatted/Source switch and opens in
preview. Remote previews remain read-only. Save changes before closing a private
draft.

Preview and Edit are modes of one document screen. Switching between them keeps
the same draft and does not add a Back step; Back returns directly to the screen
that opened the document.

## Save As and closing

Cancelling Save As or dismissing its picker returns to the document that opened
it, including an unsaved new draft. It does not switch to an earlier open file.
When closing asks you to Save, Discard or Cancel, Cancel keeps the document open;
a failed save keeps edits available for retry. If the document changes while a
close prompt is open, its old answer is ignored rather than applied to the new
state. Return to the document and close it again if needed.

## Show a document's folder

Choose **Show in folder** from the document's **…** actions menu to browse its
source in Workspaces with the file selected. The reader stays open in its
original tab, including unsaved text. On iOS, Back in that browser moves through
parent folders, then returns to the Workspaces overview at the storage root.

The action appears for folder-backed local, encrypted and remote documents.
Local imports opened from the app's file browser retain their source location
for the current app run. Imported copies without a known accessible source,
older app-owned documents and locked private sessions omit the action.

## Books and comics

Open supported EPUB books and CBZ/ZIP comics in their readers. Reader controls
include navigation and Appearance. Reader settings are separate from the general
Markdown font-size preference. Text has its own font size under Settings → Text,
and EPUB under Settings → EPUB. Pinch with two fingers in a reader or editor to
change that format’s size (12–32); it is saved on this device. Markdown source,
formatted editing and preview share one size, and text viewing and editing share
one size. Existing shared sizes migrate to all three settings.

Settings → Books & Comics → Saved books & comics lists retained imports and their
space usage. Close removes an open view. Delete local copy removes that retained
import and its reading records after confirmation; it leaves the original source
file alone.

## Remote files

Open configured remotes from Workspaces or Remote files. Supported remote documents
open read-only in memory within the reader limits. Direct remote reading does not
automatically create an offline copy. Use Workspaces's managed Pull workflow when
you want an offline Local or LocalCrypt folder.

[Remote and offline files](remote.md) explains the difference.

## Related pages

- [Reading and editing on mobile](reading-and-editing.md)
- [Document workflows](workflows.md)

## Markdown images from Local, LocalCrypt and Remotes

Folder-backed Markdown displays WebP, PNG and JPEG images in preview and formatted
editing. Both `![Photo](images/photo.webp)` and `![[images/photo.webp]]` resolve
relative to the Markdown file. GIFs are supported too. LocalCrypt and remote
image bytes remain in memory. Notes Libraries also try library-root paths and
common attachment folders when a relative image is missing.
See the [Text Editor mobile guide](../../features/text_editor/user_mobile/user_mobile.md#images-in-folder-backed-markdown)
for supported paths and image limits.

## Favourite files

Choose **Favourite file** in an opened document's **…** menu. Home lists favourites
above Recent, with a Remove control. Favouriting a file again updates how it opens;
a note favourited inside Notes Library reopens inside that library. Session-Only
references use the credential ZIP password for encryption and remain hidden until
that credential is unlocked.
