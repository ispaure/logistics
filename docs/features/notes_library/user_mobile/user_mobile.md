# Notes Library on mobile

[Notes Library guides](../notes_library.md)

Enable **Settings → Features → Notes Library**, then open **Documents → Libraries**. Text Editor and Notebooks have separate toggles. Use **New Notes Library…**, choose storage and a parent folder, enter a name and tap **Create library here**. The app creates a folder with a `.noteslibrary` marker. Local folders store plaintext. Use unlocked LocalCrypt for encrypted copies.

## Notes Library and Documentation Library

Discovery checks the storage root and two levels down for `.noteslibrary` or `.obsidian`. Open deeper libraries through File Browser. Download or sync cloud folders locally first. Documentation Library is the built-in guide viewer and its sidebar supports browsing and search.

### Open, edit and organize

- Use **New Document** for Markdown or Remarkable Document. Pick a name and folder inside the library. Tap the pencil to edit a note. **Contents…** jumps to headings, **Find / replace…** opens Source search, and **Properties…** or **Edit YAML…** edits draft frontmatter. See the [mobile editor](../../text_editor/user_mobile/user_mobile.md).
- Save, discard or cancel before leaving an edited note. A failed save keeps the draft. Markdown is limited to 16 MiB. Above 1 MiB, use Source editing. For notebooks, **Note actions → Save a copy…** exports a separate editable copy.
- In **Files**, tap a folder name to open `Folder/Folder.md` or tap its arrow to expand. Tap the breadcrumb to open a landing note or reveal its folder. Swipe along the breadcrumb to reach earlier folders.
- Hold an entry or tap **…** for **Rename…**, **Move…**, **Copy…** and **Delete…**. Existing destinations are protected. Renaming a folder also renames its matching landing note. File links keep their original paths. Confirmed deletion permanently removes the selected entry and its contents.
- Open supported source files and use **••• → Save** or **Find / replace…**. PDFs scroll, videos open the native player and Markdown embeds play inline or with **Play fullscreen video**. See [source types and limits](../user/user.md#embedded-source-files-in-notes-library) and [data views](../user/user.md#json-data-views-in-notes-library).

### Find notes and links

Open **Files** or swipe right across a note. Open **Links** or swipe left. Tap outside a floating panel to dismiss it. Wide layouts show Files beside the document.

- **Search** offers **File names** and **In documents**, including unopened folders. Use **Show more notes** for additional results. Unlocked LocalCrypt filenames use the [protected search cache](../../rclone/user_mobile/localcrypt.md).
- **Calendar** finds `YYYY-MM-DD.md` across the library. Tap a day and choose a path if needed. A missing day offers to create one in a writable library. Refresh after outside changes.
- **Links → Out / Back** lists outgoing links and backlinks. Scans stay in memory and stop at 5,000 notes, 10,000 entries or 64 MiB. `[[Tech]]` checks the note folder and root, then tries a unique match. Use `[[Topics/Tech]]` for duplicates.

Recent reopens a document in its library. Session-only visits disappear when the library closes or locks. Close returns to the screen that opened the library.

### Playlists

Choose **Playlist → New playlist**, name it and tap **Add Markdown**. You can also choose **Add to playlist** in a note's actions. Drag or use **Move up/down**. Use **Repair reference** for moved or unavailable notes. **Remove entry** keeps the note.

**Read aloud** resumes the queue, and **Play selected** starts another note. Time skips can cross entries. **This session** queues stay in memory. See [mobile Settings](../../../user_mobile/settings/settings.md) for lock-screen speech and playlist data clearing.
