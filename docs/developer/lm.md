# LM Chat integration

[Developer index](README.md)

`features.lm` owns the text-chat workspace and OpenAI-compatible HTTP adapter.
Its `Feature` declaration adds `lm.chat` and settings; the generic host does not
import its implementation. The `lm` sidebar glyph is additive; the reserved Misc
menu/glyph remains intact. No additional runtime dependency is required.

Conversation/profile data are under `preferences_path().parent / 'LM'`, outside
personal `configuration/` reset. Version-one JSON transcripts have stable UUIDs,
optimistic revisions, drafts, turn states and generation metadata. UI selection
holds an exclusive QLockFile edit lease; save publication also holds a short lock
while checking revisions. Qt's dead-process lock handling allows crash recovery.
Only a page that acquires the lease marks a saved streaming response interrupted.
Original malformed or future-version records are preserved.

The conversation tree mirrors nested directories under `LM/conversations`.
New folder and Move actions create real directories and move the corresponding
JSON. Flat version-one records remain supported; the optional `folder` field is
derived from physical placement on read. Global ID lookup detects duplicate files
across folders, preserves them and blocks ambiguous edits. Moves use the existing
publication lock and stable root-level ID lease, preserve the source until the
new record is published without replacement, and advance optimistic revisions.
Folder paths are relative, portable and do not traverse links. Search spans all
levels. Server profiles remain in `LM/profiles.json`, independent of this hierarchy.

The composer handles Enter to send and Shift+Enter for a newline, with an input
method composition guard. Send/Stop shares the composer container; message copy
controls and the latest-reply retry control live in bubble footers. The transcript
emits retry requests to the page, which owns request/lease enablement. Empty save
errors are hidden so the shared status line remains at the bottom. No
application-wide Return shortcut is installed.

The transport reads content types through `QNetworkRequest.KnownHeaders`, keeping
SSE and JSON detection compatible with Qt 6.12's changed raw-header name binding.
The page owns one QtNetwork request at a time. Sending persists a turn before
starting inference; deltas/checkpoints retain partial responses. Cancellation is
distinct from failure. Requests do not run at discovery, construction or refresh
of the conversation list. Close participation uses `can_close`, `prepare_close`
and `idle`; no feature worker is destroyed while live. API tokens live only in
the page's session memory and never in profiles, conversation metadata or exports.

Context consists of system instructions, recent whole completed turns and the
latest user prompt. Older omitted history remains saved; failed/partial turns are
excluded. Budgeting is approximate and the model context limit is configured by
the user. The UI does not promise cross-conversation memory or model training.

See [implementation contracts](../../Python/features/lm/README.md) and
[user behavior](../../Python/features/lm/user_docs/README.md). Code mode adds a bounded read-only execution contract: a conversation selects an
IDE registration, snapshots open editor text on the GUI thread, and offers
list/search/read tools scoped to that root and its exclusions. Ordinary Chat
continues rejecting tools. No mutation or shell tool is provided. `agent.py` owns
the HTTP/tool loop and cooperative ResultWorker lifecycle; busy remains true
through tool execution and subsequent requests. Tool definitions/results share
the configured context budget. JSON response metadata retains tool activity;
legacy records default to Chat. See the implementation contracts for limits.

## Organization and controls

Conversation pinning is an optional boolean in the existing version-1 record;
legacy records default to unpinned. Forks get a new conversation ID and fresh
message IDs, while preserving message timestamps and text. Tree drops request
page-owned storage operations instead of allowing Qt to rearrange rows alone.
Folder moves hold the publication lock and all descendant conversation leases,
then perform one no-overwrite rename. Actual file placement remains authoritative
for folder names, so moving a subtree does not rewrite each JSON file.

Message timestamps render locally from the existing `created` field. The LM footer
uses QStatusBar with the browser workspace's 10/8/10/8 content margins and a
zero-margin StatusLine. Chat action buttons share one accessible construction
helper. Context menus and header menus reuse the same actions and enabled state.

## Mode-specific conversation navigation

Chat/Code are sidebar tabs above the conversation browser. The persisted mode
is a conversation property, set on creation rather than changed by navigation.
Browser records/searches filter by mode; legacy records appear in Chat. Switching
saves the outgoing draft before releasing its lease and restores the target
mode’s last conversation, or opens/creates one if needed. Save failure vetoes
the switch. Tabs are disabled during both HTTP and tool work. Folder placement
and storage identities remain shared, so existing leases and moves still apply.

HTTP 400 diagnostics retain at most 16 KiB of JSON error text internally for
static classification (no loaded model, unavailable model, context limit). Raw
server text is never displayed or persisted; unknown errors retain the generic
message. Authentication error bodies remain ignored.

## Pasted screenshots

Composer accepts clipboard image MIME data, converts it to bounded PNG records,
and shows removable native previews. Optional `draft_images` and message `images`
fields are additive to version-one JSON; legacy text conversations still load.
Images are embedded, so revision-checked publication, moves, forks and exports
retain them without external paths. Draft clearing and save-failure rollback
operate on text and images together. User bubbles render separate native image
widgets; Markdown's resource-loading restrictions remain in force.

OpenAI-compatible requests use image_url data URLs in user content arrays. Recent
complete turns retain their images, while omitted/failed turns follow existing
context policy. Budgeting uses a documented image-token reserve rather than
base64 length, including Code-mode continuations. Vision support must be supplied
by the configured model/server; text-only payloads retain their original shape.

Local file URLs take precedence over clipboard imageData: macOS Finder can offer
a generic file icon as imageData for a copied screenshot. The file loader uses
bounded bytes and QImageReader format/dimension checks, accepts raster formats
only, and reports unreadable files without falling back to their icon preview.
Direct screenshot pixels still use the original image MIME path.

Composer and LMPage explicitly accept image/file-URL drag events and route drops
through the same bounded clipboard decoder. They do not insert file:// text for
image files. Ordinary text drops retain the editor’s native behavior.
