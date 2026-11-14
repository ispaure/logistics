# LM Chat

LM Chat uses a model running on your LM Studio or compatible chat server.
Logistics keeps the conversation and draft on your computer and sends the
request to the selected server.

## Connect and start a conversation

1. Enable **LM Chat** in **Settings → Features** if it is hidden, then open it
   from the landing page or sidebar.
2. Start your server and load a model. In **Manage server profiles**, enter the
   API base URL, such as **http://localhost:1234/v1** for LM Studio. Use the
   server's address when it runs on another computer.
3. If the server requires authentication, enter its **Session token**. Tokens
   stay in memory and must be re-entered after restarting. Use HTTPS for an
   authenticated remote connection.
4. Refresh the server's model list. Select a model beside Send, then open a
   **New conversation**. **Enter** sends and **Shift+Enter** adds a line.

The stop square cancels a request and retains partial output. You can draft
another question during generation. Use **Retry / Regenerate last response**
to ask again and keep the previous response in the transcript. Use **Copy
message as written** for the reply's source text or **Copy code** in a code
panel. The speaker reads a completed reply using the system voice. Manage
background reply notifications under **Settings → LM Chat → Options → Chat**.

## Attach files and paste screenshots

Use **+ → Attach text files…** or **Attach images…**. Paste or drop screenshots
into the composer. Remove anything you do not want to send. Text attachments
and the draft share a 64 KiB limit. You can attach up to four images. Raster
inputs up to 16 MiB are resized before saving, with a 2 MiB limit per saved
image. The conversation has a 32 MiB save limit.

Screenshots need a vision-capable model and server. They are sent to that
server when you send or regenerate, and recent screenshots may be included in
later context. Drafts, history, forks and exports can retain the images.

## Discuss an IDE project in Code mode

Choose **Code** and select an IDE project. Use **Refresh projects** if the
project is missing. **Paste Selection** includes selected IDE text, including
unsaved edits. Review it before sending. Compatible models can list, search
and read project text. Logistics sends those tool results to your selected
server. Tools respect project exclusions and refuse paths outside the project.

**Allow edits** is off by default and is saved per conversation. Turning it
on lets the model replace matching text in existing project files. Successful
edits save immediately without a confirmation dialog and appear as unstaged
changes. Tools cannot run commands, create or delete files, or stage changes.
Stop prevents subsequent edits. Edits already saved remain on disk.

Use **Edited files → View changes** to inspect the saved diff or **Undo** to
revert that reply's changes where their text and context still match. Save or
reload stale editors before retrying. Undo keeps edits elsewhere and preserves
the Git index. If it stops partway, check the list of reverted files before
retrying.

## Generation settings and context

Expand **Generation settings** for sampling, model context size, maximum
response length and system instructions. Match the context size to the model
actually loaded on your server. Logistics reserves room for the reply and
drops older turns from the request as needed. The saved transcript stays
complete. Stopped and failed turns stay out of future context until a retry
completes.

New conversations use defaults under **Settings → LM Chat**. Existing
conversations keep their saved settings. If a model loads slowly, increase the
inactivity timeout. Its default is 180 seconds without incoming data.

## Saved conversations and recovery

Drafts save automatically. After a crash, the last checkpointed reply is
marked interrupted. An open conversation can only be edited in one Logistics
window. Close it in the other window to reopen it.

Use **Export…** to keep a JSON or Markdown copy outside the LM storage folder.
JSON retains drafts and generation metadata. Conversation files are plain JSON
in your local app data and are kept when personal configuration is reset.
If saving reports a disk conflict, export the current copy before reopening.

## Troubleshooting

- **Connection failed.** Check that the server is running, the API URL is
  reachable and remote access is allowed by the server and firewall.
- **Authentication failed.** Re-enter the session token.
- **No model available.** Load one on the server, refresh and select it.
- **Request rejected.** Check the model context, output budget and supported
  parameters. Code tools and screenshots require server support.
- **Stream interrupted.** Check the partial text, then retry when the server
  is ready. Use the final API URL if the server returns a redirect.

## Organize conversations and page controls

Use the conversation's **…** menu or right-click to pin, fork, rename, move,
export or delete it. A fork copies the saved conversation and draft without
contacting the server. Deleting permanently removes the saved conversation
after confirmation. Export it first if needed.

Create folders with **New folder…**, then drag conversations into them or use
**Move conversation…**. Search finds titles and message text across folders.
Use **Refresh** to pick up changes from another window. Conversation switching
and dragging are paused during a request.

## Mobile development builds

See [LM mobile workflows](../user_mobile/workflows.md#mobile-development-builds).
Saved conversations stay on the device where they were created.
