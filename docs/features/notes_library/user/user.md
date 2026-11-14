# Using Notes Library

[Notes Library guides](../notes_library.md)

Select **Notes Library → Open Library** and choose a Local or unlocked LocalCrypt folder. Download cloud folders first. Each library has its own workspace tab. Choose **Edit Markdown** on an existing note, then **Formatted** or **Source**. **New Document** creates Markdown or, with Notebooks enabled, an `.rmdoc` drawing. Save, discard or cancel when leaving an edited document. A failed save keeps the draft. Notes are limited to 16 MiB.

## Notes Library and Documentation Library

Workspaces offers **Open as Notes Library** for folders marked with `.noteslibrary` or `.obsidian`. Notes Library uses filenames and supports file organization. Documentation Library uses page titles and its sidebar is for browsing.

- **Files** shows the tree. Click a folder name to open its `Folder/Folder.md` landing note, or expand its arrow. A breadcrumb click opens the landing note or reveals the folder in Files. **Alt+Left/Right** follows the active tab's history.
- **Search** offers **Search in File Names** or **Search within Documents** for supported text files. Separate keywords must all match. Quote a phrase to match its word order. **Show more notes** loads more results.
- **Calendar** opens `YYYY-MM-DD.md` notes wherever they are stored. A missing day offers to create one at the root. Use **Refresh daily notes** after outside changes.
- **Links** lists outgoing links, backlinks, unresolved links and counts. A link such as `[[Tech]]` checks the current folder and root before looking for a unique match within 10,000 entries. Use explicit paths for duplicates.

In writable libraries, use **New folder**, **F2** to rename, or right-click for **Rename…**, **Move…**, **Copy…** and **Delete…**. Drag an item onto a folder or empty sidebar space to move it. Moving resolves unsaved edits first and preserves history. Existing destinations are refused. Links keep their original paths. Renaming a folder also renames its matching landing note. Permanent deletion includes descendants and requires confirmation.

### Playlists

In **Playlist → New playlist**, name the queue and use **Add Markdown**, or choose **Add to playlist** from a note. Drag entries or use **Move up/down**. Use **Repair reference** for a missing note. **Read aloud** resumes this queue's saved place, and **Play selected** starts another entry. Time skips cross entries. Removing entries or deleting the playlist keeps source notes. **This session** queues stay in memory.

For external vault launching, see [Obsidian desktop integration](../../obsidian/user/user.md).

## Embedded source files in Notes Library

Open Markdown, notebook, image, PDF, video and source files in Files. Videos open the full Video Player. In Markdown, `![[clip.mp4]]` plays inline from the start when you press Play. Attachment resolution checks beside the note, the root, then a unique match. Specify a path to resolve ambiguity. Images use an 8 MiB and 16-megapixel limit. PDFs use 32 MiB.

Source types include JSON/JSONC, JS/MJS/CJS, CSS, TXT, CSV, YAML/YML, TOML, INI, XML, HTML, PY and TS. Use Save and Find/Replace in the source editor. Saves keep encoding and line endings and refuse externally changed files. LocalCrypt plaintext stays in memory. Read-only locations stay read-only. Source files have a 16 MiB limit. Hidden configuration is excluded.

## JSON data views in Notes Library

Supported `dataviewjs` blocks run automatically in reading mode and leave the authored block intact. Reopen the note to reload changed data. For `data/items.json` use

```dataviewjs
const rows = JSON.parse(await dv.io.load("data/items.json"));
dv.table(["Name", "Quantity"], rows.map(row => [row.name, row.quantity]));
```

Call reusable scripts with `await dv.view("views/inventory", {path: "data/items.json"})`. Save the script as `views/inventory.js` or `views/inventory/view.js`. It receives `dv`, `dataview` and `input`. Plain load paths try the library root then the note folder. Explicit relative paths use the note folder and must stay inside the library. Extensionless loads may resolve to JSON. Missing text returns `undefined`. Invalid JSON, missing scripts and unsupported APIs show block errors.

Use `dv.table`, `dv.list`, `dv.header`, `dv.paragraph`, `dv.span` and `dv.fileLink` for display. `dv.current().file` describes the note. `dv.pages('"Folder"').array()` lists Markdown paths in a folder tree. `app.vault.getMarkdownFiles()` includes paths and `stat.size`. `dv.container.createEl` supports detached lists, links, paragraphs and spans. Full Dataview, Obsidian plugins, browser DOM and `view.css` are unsupported.

Runs have no network or host write access. Limits include 64 blocks, 128 file requests, 2 MiB per file, 8 MiB overall and 30 seconds. Closing, locking or switching notes retires the run. LocalCrypt content stays in memory.

## Notes Library document groups

Open a file with **Open in new tab** to keep the active document. Drag an inner tab to reorder or split into up to three groups. Tabs retain drafts and back/forward history. Save applies to the focused tab. **Links** visibility is remembered per document tab.
