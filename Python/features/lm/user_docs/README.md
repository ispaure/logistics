# LM Chat

LM Chat connects Logistics to an existing LM Studio or OpenAI-compatible text
chat server. The server loads and runs the model; Logistics keeps the interface
and conversation history on your computer. This feature does not install models
or execute tools, commands or file edits.

## Connect and start a conversation

1. LM Chat is disabled by default. Enable **LM Chat** in Settings → Features,
   then open it from the launch cards or sidebar. Existing personal feature
   choices override the shipped default.
2. Start your server and load a chat model there. For another computer, configure
   its server to accept connections from your Logistics computer.
3. Click the server settings icon beside **Server** to add or edit named profiles.
   Its tooltip is **Manage server profiles**. Enter the complete API base
   URL, usually `http://localhost:1234/v1` for LM Studio. A remote server uses its
   own address, e.g. `http://192.168.1.20:1234/v1`. Do not append `/chat/completions`.
4. If authentication is required, click **Session token** to reveal the optional
   **Token** field. Tokens remain in
   memory for this page/session and must be re-entered after restart; they are not
   saved in profiles, transcripts or exports. Use HTTPS for authenticated remote
   connections unless you trust the network carrying the token and conversation.
5. Click the refresh icon beside **Model** to test the connection and refresh
   models. Select a model, or type its exact model ID if
   the server does not offer model discovery.
6. Click the **New conversation** icon, type a message and click the send arrow.
   **Enter sends**;
   **Shift+Enter inserts a new line** in the message composer.

Output streams into the transcript. The send arrow becomes a stop square while
generation or a connection check is running. Clicking it cancels the client request and saves
partial output. The server may need time to notice the closed connection. One
request runs at a time on a page; conversation switching is disabled during it.
You can draft your next question while a response streams. Enter does not start
a second request until the current request ends; the draft is kept and autosaved.
Markdown and code blocks are displayed. Transcript links and embedded resources
do not open automatically. Select text to copy it, or use the **Copy message as written**
icon beneath a message. **Retry / Regenerate last response** sits beside the copy
icon beneath the latest assistant reply. Icons have tooltips and accessible names. Conversation
rename, move, export and delete actions live in the **Conversation actions**
(three dots) menu above the tree.

The transcript and composer use the shared Markdown reading font and size from
Appearance settings. Code blocks use the shared monospace code font and size,
with continuous panels, language labels and syntax colors for recognized languages.
Triple-backtick and longer fences, including `vbnet`, are supported. Stored server
text is preserved; formatting does not rewrite the response.
Leading/trailing blank lines and code indentation in sent messages are preserved.
Each bubble has a copy icon that copies its original text, including Markdown
fences. Reopened failed responses show their saved error details beside the text.

Messages appear as a conversation: your messages are grey bubbles on the right,
and assistant replies sit on the left. Earlier message selections stay intact
while a new reply streams. The composer grows for additional lines up to a bounded
height, with Send/Stop in the same input row. A muted reminder above the input
reads “Language Models can make mistakes. Check important info.”
Connection/generation messages use the shared muted footer; hover over a
shortened status to read its full text. Save failures remain visible separately
with recovery/export instructions.

## Generation settings and context

Expand **Generation settings** to adjust temperature, top-p, maximum response
tokens, model context size and system instructions. Server default omits the
corresponding sampling parameter. Settings are saved per conversation. Changing
them affects subsequent requests, including regeneration. A server/model may
reject parameters it does not support.

Set model context size to match the model's actual loaded server configuration.
Logistics uses an approximate UTF-8 token estimate, reserves the maximum response
tokens, and includes recent completed user/assistant turns. When older turns do
not fit, they are omitted from the request and counted in the generation status.
The full transcript stays on disk. A newest message that cannot fit is rejected
locally rather than truncated. The estimate is not the model's tokenizer; a server
can still reject a request for context overflow. Lower the history/response budget
or adjust context size to match the server when that happens.

Failed, stopped and interrupted turns are excluded from future context unless a
retry produces a completed answer. **Retry / Regenerate last** resends the latest
user turn without duplicating that user message. Previous assistant alternatives
remain in the transcript; future requests use the latest completed alternative.
Regeneration preserves any draft for your next question.

Each conversation has its own history. There is no automatic memory across
conversations, model training, summary generation or document retrieval.

Feature-wide defaults and the inactivity timeout are in **Settings → LM Chat**.
New conversations inherit current defaults. Existing conversations retain their
saved generation settings. The default timeout is 180 seconds without incoming
data; increase it for a slow-loading model. No request is made just by opening
the page or starting Logistics.

## Saved conversations and recovery

Conversations appear in a folder tree. Click **New folder…** to create a folder
using the folder-plus icon above the tree, under the selected folder (or the
selected conversation's folder). You can enter
several levels at once, for example `Projects/Planning/2026`. Select a folder and
click **New conversation** to save a new conversation there. **Move conversation…**
in the three-dots menu moves the open
conversation and its JSON file into another folder; enter a new nested path or
choose `/` to return it to the root. Empty folders remain available for reuse.
Folder names use `/` between levels and cannot contain `..` or special filesystem
path characters. Folder creation and moves preserve conversation IDs, drafts and
history. The tree is collapsible; Refresh keeps collapsed branches and the selected
folder. Starting a new conversation clears a search filter and reveals the new
conversation in its folder. Opening another conversation shows its latest messages;
scrolling upward during a reply keeps your position instead of following new text.

Search matches titles and message text across all folder levels, showing matching
conversations with their parent folders. Select a conversation to reopen it.
**Rename** changes its title. **Delete** permanently removes its saved JSON after
confirmation; export a copy first if needed. **Refresh** reloads the conversation
list after changes in another window.

The macOS storage directory is:

```text
~/Library/Application Support/Logistics/LM/
    profiles.json
    conversations/<conversation-id>.json
    conversations/Projects/Planning/2026/<conversation-id>.json
```

Windows uses `%APPDATA%/Logistics/LM` with the application's normal home fallback.
Linux uses `$XDG_CONFIG_HOME/logistics/LM` or `~/.config/logistics/LM`.
**Server profiles are stored in `LM/profiles.json`**, separate from conversation
folders. The file contains server IDs, names and API base URLs; it is created when
you save the server profile editor. Before that, **LM Studio (localhost default)**
is supplied as a built-in fallback. API tokens are not saved in this file.

These files are private user data outside the checkout and outside resettable configuration.
Resetting personal configuration does not delete conversation history. Transcript
files are plain JSON, not encrypted; ordinary file backups can include their text.

Draft/settings changes autosave after a short pause. A user turn is saved before
its request starts; streaming output checkpoints once per second and at the end.
After a crash, the last saved partial response is marked interrupted on reopen.
The last uncheckpointed portion may be missing. An open conversation is locked
against editing in another Logistics window; close it in the first window to
reopen it in the second. Dead-process locks are recovered by Qt.

Save errors remain visible and stop generation at the next checkpoint. The
current copy remains available for **Export…** as JSON or Markdown. JSON includes
drafts and generation metadata; Markdown includes the transcript and partial
response status. Exports must go outside LM's storage directory. A conflicting
disk revision is not overwritten; export your current copy before reopening.
Malformed/unsupported files are retained and reported, rather than replaced.
Existing root-level conversation files remain supported. JSON files moved into
real subfolders manually are found on Refresh; their physical location determines
their folder. Close the conversation before moving it outside Logistics. Duplicate
copies with the same conversation ID are reported and preserved rather than
opened or overwritten.

## Troubleshooting

- Connection failure: check that the server is running and its API base URL is
  reachable. For remote servers, check binding and firewall configuration.
- Authentication failure: enter the correct session token.
- Missing model: refresh models or enter the exact model ID; load it on the server.
- Rejected request: check context size, output limit and supported parameters.
- Interrupted stream: partial text is retained; retry when the server is ready.
- Redirects are reported rather than followed. Enter the final API URL directly.

LM Studio's OpenAI-compatible text endpoint is the initial target. Other servers
must support Chat Completions with text messages; model discovery uses `/models`.
Image/audio inputs, server provisioning, persistent token storage, Codex and local
tool execution are outside this first version.

## Organize conversations and page controls

Right-click a conversation for **Pin / Unpin**, **Fork**, **Rename**, **Move**,
**Export**, or **Delete**. Delete still asks for confirmation. Pinned conversations
appear first within their folder and keep their pin after reopening. Fork creates
an independent saved copy of the full conversation and draft; future changes do
not alter the original, and forking does not contact the model server.

Drag a conversation onto a folder to move it. Drag a folder onto another folder
to move its entire subtree; drop on Conversations or empty tree space to return it
to the root. Folders cannot be dropped into themselves/descendants or overwrite
an existing folder. A move is refused if another window owns a chat inside it.
Conversation switching and dragging are disabled during a request.

The page has File, Edit, Conversation, View and Server menus. Edit commands target
the draft. View can hide the conversation sidebar or show generation settings.
The compact bottom status bar matches the file-browser workspace spacing.
Each message shows its creation time in small grayscale text; hover for the full
local date, time and timezone. Older messages without usable timestamps omit it.
