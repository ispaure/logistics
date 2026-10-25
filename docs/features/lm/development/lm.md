# LM Chat integration

[Developer index](../../../development/development.md)

`features.lm` owns the text-chat workspace and OpenAI-compatible HTTP adapter.
Its `Feature` declaration adds `lm.chat` and settings; the generic host does not
import its implementation. The `lm` sidebar glyph is additive; the reserved Misc
menu/glyph remains intact. No additional runtime dependency is required.

Desktop presentation lives under `Python/features/lm/ui/`: `page.py` coordinates
navigation and generation presentation, `generation.py` coordinates request
preparation/publication/transport over captured inputs, `layout.py` builds widgets, and composer,
profile, transcript, image and IDE-context modules own their specific UI work.
The root `session.py` owns the conversation record, edit lease, dirty state and
response transitions independently of widgets. See the feature's
[module map](development.md) before changing these owners.
Old root-level presentation imports remain compatible; registration uses the
new package lazily. Mobile also consumes the shared generation/session owners
through its own execution adapter; see the
[shared lifecycle contract](development.md#shared-desktop-and-mobile-generation).

Mobile `ChatUI.show_chat` retains profile admission and lazy initial selection;
named builders assemble input/transcript controls, configuration and the retained
workspace in their original order. `_project_chat_rows` updates recycled rows
under the native selection guard without selecting a new record itself. Desktop
`LMPage._bind_session_controls` retains timers and transport/widget bindings;
`_populate_conversation_tree` projects records while `refresh` retains the signal
guard, prior selection and expansion restoration. Neither path adds chat state.
Transcript workers still capture the conversation and render generation, rejecting
stale results. Session leases, drafts typed during generation, cancellation,
session-only keys and the distinct desktop tools/mobile text policies retain their
existing owners and contracts.

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
emits retry requests to the page, which derives request/lease enablement from its
client and session. Empty save
errors are hidden so the shared status line remains at the bottom. No
application-wide Return shortcut is installed.

The transport reads content types through `QNetworkRequest.KnownHeaders`, keeping
SSE and JSON detection compatible with Qt 6.12's changed raw-header name binding.
The page dispatches through one request client at a time. The session publishes
the pending turn before inference and rolls back response insertion/draft clearing
if publication fails. Deltas update session-owned response state; the page's
GUI-thread timers schedule rendering and persistence. Cancellation is
distinct from failure. Requests do not run at discovery, construction or refresh
of the conversation list. Close participation uses `can_close`, `prepare_close`
and `idle`; no feature worker is destroyed while live. API tokens live only in
the page's session memory and never in profiles, conversation metadata or exports.

Context consists of system instructions, recent whole completed turns and the
latest user prompt. Older omitted history remains saved; failed/partial turns are
excluded. Budgeting is approximate and the model context limit is configured by
the user. The UI does not promise cross-conversation memory or model training.

See [implementation contracts](development.md) and
[user behavior](../user/user.md). Code mode adds a bounded project execution contract: a conversation selects an
IDE registration, snapshots open editor text on the GUI thread, and offers
list/search/read tools scoped to that root and its exclusions. An optional
`allow_edits` toggle enables conflict-checked exact text edits to existing files. Ordinary Chat
continues rejecting tools. Edits save directly after live editor validation on the GUI thread; no shell tool is provided. `agent.py` owns
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

## Mobile native action placement

Chat declares New Conversation and its action menu as screen-level toolbar
controls for the iOS host. The conversations drawer occupies the leading native
navigation group; UIKit owns its horizontal or Duo vertical placement. The
composer and Send/Stop remain in the message pane. Sidebar settings uses a
preferences symbol so ellipsis remains reserved for overflow. The feature keeps
its conversation title/model content and command callbacks; Android retains its
existing header layout.

## Mobile server setup

Android and iOS share `mobile/ui.py` and `mobile/transport.py`. Setup labels the
server address, optional session key and model separately. **Connect & load
models** needs no model ID; it retains the current model when listed, otherwise
selects the first result, and persists the selection. Manual IDs remain available
for servers without model discovery. Invalid saves stay in setup with feedback.
Selection-list replacement suppresses change callbacks until the intended model
is restored, so refreshing does not silently replace it with the first model.
Initial conversation discovery can complete while a connection request owns the
controls. Keep the initial selection pending during that request and refresh it
when the controls become idle, so an existing draft is restored or an initial
conversation is created before sending. `mobile_build/tests/chat/test_chat_inventory.py`
checks both an existing conversation and an empty library under this ordering.

`mobile_api_url` adds `/v1` only to addresses with no API path; profile validation
and the HTTP client use the same normalization. Explicit paths remain unchanged.
Connections/model discovery retain a 15-second timeout. After connecting, chat
requests use a 120-second socket idle timeout, including waiting for response
headers, to accommodate model loading. Diagnostics distinguish connection,
first-response and stream idle timeouts without exposing credentials or server
response bodies. Cancellation still interrupts the socket and worker queue.
The ten-minute generation deadline is checked between event reads; a pending
read remains bounded by the socket idle timeout.

Focused verification: `Python/tests/test_mobile_chat.py` checks URL normalization,
request paths, timeout stages and cancellation; `mobile_build/tests/chat/test_chat_ui.py`
checks discovery without a model, selection persistence and validation feedback
through Toga's dummy backend. Native device layout and real-server behavior need
separate Android/iOS verification.

Android keyboard layout uses the shared navigation adapter's removal of
Material's automatic IME padding from bottom navigation. The scrolling transcript
has a zero minimum height, and the composer caps growth at one quarter of the
native container height (52–120 logical units), so the keyboard-reduced viewport
does not clip Send or overlap navigation. `chat_keyboard_probe.py` in the native
test owner exercises an isolated app with no server, long header/model labels,
multiline drafts and repeated keyboard opening/closing. It checks actual native
rectangles, keyboard visibility, bar height and retained draft text.

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
