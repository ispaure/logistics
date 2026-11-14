# Text editing on mobile

Enable **Text Editor** in Features. Open or create the document from Documents or Workspaces. Markdown opens in preview. Tap **Edit Markdown** for formatted editing or **••• → Source editing** for exact syntax. **Formatted editing** switches back and **View document** opens preview. Both editors use the same draft. Tap **Save** to publish.

## Plain text, storage and platform scope

Ordinary text and source files use the native editor with a language dropdown. **Find and replace…** searches the current source buffer. The standalone editor accepts up to 1 MiB. Desktop merge, multiple cursors, folding and split view are unavailable.

Edit Local or unlocked LocalCrypt files. Copy a cloud file locally to edit. Ordinary drafts have private recovery. LocalCrypt drafts are session-only, so save before closing or locking. Failed saves keep edits. Use **Save a copy…** after an external change.

In Markdown, type headings or emphasis markers or use the formatting toolbar. Use **Format → link** for a URL or relative path. **Find in this page…** searches preview and **Find and replace…** searches Source. Pinch to resize Markdown text. **Settings → Markdown → Justify text** reflows paragraphs and lists without rewriting the source. Use **Read aloud…** for the selected text or the rendered note.

**×** closes and prompts when dirty. **Document actions → Delete document…** permanently deletes an app-stored file, its recovery and Recent entry after confirmation. Close other app windows first. Files opened from a folder use that folder's actions.

See [Documents and editing](../../../user_mobile/documents/documents.md) and [Reading and editing](../../../user_mobile/documents/reading-and-editing.md#markdown-read-aloud).

## Images in folder-backed Markdown

Use a path such as `![Photo](images/photo.webp)` or `![[photo #1.png|400]]`. Size hints accept a width or both dimensions, such as `|400x200`. Notes Library also checks its root and Attachments, Assets and Images folders. Standalone imports may lack access to siblings, so open the source from its folder.

PNG, JPEG, GIF and static WebP use an 8 MiB and 16-megapixel limit per image and 16 MiB per render. Missing images show alternative text. LocalCrypt image bytes stay in memory. Paths must remain inside the provider root.

## Lock-screen speech

Session-only background read-aloud requires an explicit opt-in. See [Speech while locked](../../../user_mobile/settings/settings.md#speech-while-locked).

## Notes Library and Documentation Library

See [mobile Notes Library](../../notes_library/user_mobile/user_mobile.md).
