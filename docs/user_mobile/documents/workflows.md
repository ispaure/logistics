# Document workflows

## Document workflow

The app opens on **Home**, a landing page with quick access to files, editors,
books/comics and chat. The house icon is the first native destination, before
**Folder Hub**, **Documents**, **Chat** and **Settings**. **Folder Hub** separates rclone, ordinary Local files and Network shares into source tabs, with available copies grouped under their owning source.
If folder discovery fails while credentials change, Folder Hub shows an error
with **Refresh**, **Browse local files** and **Connections…**. Retry there after
the connection is ready; restarting the app is unnecessary.
Tap a folder to browse its preferred available copy directly. The **•••** button
beside a folder opens its Browse Local/LocalCrypt/Remote, Pull, Push and management
actions. The main Browse action is prominent; Delete local folder is separated
and uses destructive styling. Pull/Push direction is shown for mapped copies.
Deletion still requires confirmation, and Push retains its existing review. Local browsing uses app-managed files rather than
the entire device filesystem. Choose **Documents → New** for **Plain text (.txt)** or **Markdown (.md)**.
Books and comics are available through Folder Hub or Home’s Books & Comics panel;
Chat has its own bottom navigation button between Documents and Settings. Native tab
controls adapt to the Apple layout; Android uses bottom navigation in compact
windows and a rail at 600 dp or wider. Switching destinations retains each
screen. **Folder Hub** returns to the folder list and **All documents** returns
from the editor to the Documents hub.

Back returns through screens within the current destination. It does not switch
tabs or close a document. iOS uses its native navigation stack and Back control;
Android uses the lifecycle-owned AndroidX Back dispatcher. At a destination root,
Android yields Back to the system. Existing save/checkpoint failures block a
Back action that would leave the screen.

Choose a document from **Open documents** in Documents or **Recent** in its menu,
or use **Actions → New document**. Edit its name in the name field and
its contents in the text area. **Save** publishes the edited file inside the app.
Text, source files and Markdown share the native source editor. Markdown can
show a live formatted preview while you edit. See [Text and Markdown](documents.md#text-and-markdown).

Each open text/Markdown document owns its editor and draft. **New**, opening a
stored document, and successful imports add it to **Documents → Open documents**;
opening the same stored identity again activates it. Documents with the same name
remain separate. Switch using Open documents or Recent. Closing a document keeps
its stored data; the six most recent ordinary documents can be reopened from Recent.
**Close** removes an item from that list without deleting its stored document.
For an ordinary unsaved document, choose **Save and close**, **Keep draft and
close**, **Discard changes and close**, or **Cancel**. Retained drafts remain on disk and recent entries can reopen them. Discard resets recovery to the current saved file without
overwriting changes made outside the editor or recreating a deleted file. A
failed save or conflict keeps the document open; use **Save a copy** to preserve
both versions. Session-only drafts offer Save, Discard, and Cancel without durable
draft retention. **Close saved documents on restart** is enabled
by default in Settings. On restart, saved text and reader sessions leave Open
documents; stored files and reading progress remain available. Unsaved text,
conflicts and unreadable recovery entries stay in the open list. Turn this setting
off to retain all ordinary open items at the next launch. There is a maximum of
32 open items. An empty workspace stays empty until you create or open a file. Their active selection resumes when **Restore last
document** is enabled; turning it off also prevents automatic EPUB/comic reopening.
You can still explicitly reopen those readers from Open documents with their saved
progress. Private resource restoration remains excluded. Native cursor/selection and scroll offsets are recorded for text views.
Opening an item from the open/stored list also resumes its Edit or Preview mode.
Back to the editor selects Edit for that document.
If a restored item is unavailable, **Try again** retries it and **Remove from
open documents** removes only its open entry. Stored files are preserved.

On regular-width Apple layouts, native split navigation keeps the document list
beside its detail view. Android shows both at 640 dp or wider and uses the
compact route stack below that threshold. Layout changes retain the same editor
and session. The editor keeps its name, text, status, Save and Preview visible;
**Actions** opens a native Apple button menu or Android popup for New, Import,
Open from Files, Save a copy, Save As, Export and Close.

**Preview** renders common Markdown offline: tables, headings, nested bulleted
and numbered lists, quotes, bold/italic/strikethrough text, rules, line breaks and
inline/fenced code. Wide tables and code blocks scroll horizontally inside the
page. Raw HTML is escaped, links are inert, and scripts/images/network resources
are blocked. Documentation additionally supports local page links and heading anchors.
Rendered HTML is limited to 2 MiB. **Back to editor** returns to the same draft.

**Export…** opens a destination picker and exports the current draft as a copy,
retaining its encoding and line endings. It does not save over the original
imported document or mark the private draft saved. Android uses a new document
request; iOS uses an export-copy picker. Cancelling preserves the document.

**Import…** opens Android's document-provider picker or iOS's document picker.
Logistics reads the selected document into a private copy. Editing or saving that
copy does not change the source file. Imports are limited to 1 MiB of text;
unsupported/binary data and unavailable permissions produce an error. Files with
UTF-8 or recognized Unicode byte-order marks retain their encoding and original
line-ending style when saved.

Draft contents and valid name changes are checkpointed during editing. Reopening
the app restores saved documents and available unsaved drafts. A malformed
recovery record is preserved and reported. If a private stored file changed or
disappeared while a draft existed, normal saving refuses to overwrite it.
**Save a copy** preserves the recovered text as another private document.

The prototype's controls have 44-point layout targets and use native
platform text fields, selection and keyboard behavior. The draft is also
checkpointed when the main window loses focus and during a normal exit. These
hooks supplement checkpoints made while editing; forced termination does not
require an exit callback to have occurred.

External sharing and editing the original provider document are not
implemented. EPUB/comics use the private library described below. Native picker grants, keyboards and suspension need testing
on devices before treating this prototype as a supported mobile product. See
[build and validation instructions](../../development/mobile-launchers.md).
