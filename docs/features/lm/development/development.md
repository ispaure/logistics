# LM feature implementation

The feature's lazy `register()` contributes `lm.chat`, the `lm` rail glyph and
typed chat defaults. Registration/page construction never make network requests.
The [user guide](../user/user.md) describes available workflows and limits.

| Module | Ownership |
| --- | --- |
| `domain.py` | Version-one records, validation, generation defaults, context budgeting |
| `configuration.py` | Central settings validation |
| `storage.py` | Platform LM root, nested folders, profiles, edit leases, optimistic revisions, export |
| `transport.py` | Qt asynchronous HTTP, bounded text/tool SSE decoding, request cancellation |
| `agent.py` | Project tool rounds, context/call limits and cooperative worker ownership |
| `changes.py` | Turn snapshot comparison and unified patch generation |
| `undo.py` | Exact-context reverse patches for guarded turn Undo |
| `project_tools.py` | Project path/exclusion checks, bounded file listing, text search, line reads and optional exact text edits |
| `session.py` | Conversation record, edit lease, dirty state, publication and streaming response transitions; no widget dependencies |
| `generation.py` | Request preparation and publish-before-dispatch orchestration over captured inputs; no widgets |
| `ui/page.py` | Navigation, UI value collection, generation presentation, GUI-thread timers, save feedback and close prompts |
| `ui/layout.py` | Top-level layout composition plus private sidebar, session-control and message-area builders; no conversation state ownership |
| `ui/composer.py`, `ui/mode_tabs.py` | Enter/Shift+Enter, screenshot paste/drop, sampling controls and Chat/Code tabs |
| `ui/profiles.py` | Identity-preserving server profile editor |
| `ui/ide_context.py` | Lazy project registration lookup and GUI-thread editor snapshots |
| `ui/changes.py` | Edited-files cards and right-hand saved diff preview |
| `ui/project_edits.py` | GUI-thread edit dispatch, live buffer validation and publication |
| `ui/conversation_actions.py` | Conversation creation, moves, forks, menus and export coordinated with the page |
| `ui/conversation_tree.py` | Tree drag requests; storage operations stay outside the widget |
| `ui/conversation_view.py` | Incremental native Markdown bubbles and bounded message sizing |
| `screenshots.py` | Bounded inline PNG records and image context reserve |
| `ui/image_view.py` | Native previews and screenshot viewer |
| `ui/icons.py` | Palette-aware toolbar and Send/Stop glyphs |

Start a desktop UI change at `ui/page.py`, record/lease changes at `session.py`,
saved-file contracts at `storage.py`, and request construction at `domain.py`.
Storage bounds reads to 32 MiB plus one byte before decoding, even when file size
metadata is stale. Oversized records remain untouched and cannot become a save
baseline; catalog listing reports its existing warning for them.
Registration imports `ui/page.py` lazily. Import presentation from `features.lm.ui`;
the old root-level forwarding modules have been removed. Layout builders populate
the existing page widget references in their original order; the page keeps
callbacks and lifecycle ownership. Request/agent adapters remain at the feature root; they do not
own widgets. Mobile uses selected portable domain, session and generation modules
plus its execution adapter, without importing desktop presentation or project tools.

`ConversationSession` receives a store and owns the active record, lease, dirty
flag and streaming response. It acquires/loads or publishes a replacement before
releasing the prior lease. Recovery marks streaming records interrupted only
after acquiring their lease. Response insertion and draft clearing publish before
network dispatch; failure restores the record and leaves it dirty for retry.
Completion clears active response ownership while retaining partial text, even
when publication fails. Storage errors propagate to the page for recovery UI.

`GenerationCoordinator` builds a request from `GenerationInputs` (captured profile,
project and editor buffers) and the conversation session. Its prepared plan holds
no token. `start` publishes the pending response before invoking the page's
publication callback and starting transport. Publication failure prevents both;
transport startup failure saves a failed response while retaining the user turn.
A secondary save failure is reported separately, leaving the session dirty for
retry/export. `test_lm_generation.py` exercises these boundaries without widgets.

The page checks transport availability and saves outgoing widget values before
switching records. It owns credentials, draft widget/image previews, timers,
transport callbacks and close decisions. Existing `data`, `lease`, `dirty` and
`active_message` accessors forward to the session rather than copying state.
Destruction captures only the session to release its lease; cooperative close
still waits for network/tool activity before releasing ownership normally.

Chat uses stateless OpenAI-compatible `/chat/completions`, with `/models` discovery.
Sampling defaults omit parameters; completed whole turns are selected newest-first
under a UTF-8 estimate of ceil(bytes/3)+8 per message, plus a 32-token envelope.
The server's tokenizer/context limits remain authoritative. Each response stores
the effective settings, endpoint, model and selected message IDs, with completion
reason/usage when supplied. No secrets enter request metadata. Prior assistant
alternatives are retained; context selects the latest completed answer per turn.

The tree mirrors real directories under `LM/conversations`, including empty
folders and arbitrary nesting subject to filesystem limits. `folder` is an
additive optional version-one JSON field; reads derive it from physical placement,
so legacy flat files and manually relocated records remain readable. Lookup and
search span folders; duplicate IDs are preserved and excluded with a warning.
Relative folder components are validated for portable names and links are not
traversed. Moves publish a new JSON without replacing a destination, then retire
the old file, advancing the revision only after success. Publication failure
preserves the source. Before retiring the source, moves verify the published bytes and recheck both
file revisions. Source retirement failure removes the new copy only while its
verified content and file revision still match, and the source remains unchanged.
A changed or missing source stops cleanup and retains the surviving copy for
recovery; it cannot cause rollback to delete the only remaining conversation. Replaced/changed copies survive
with both paths named in the conflict. If rollback also fails, remaining copies
are recoverable and duplicate detection blocks editing until resolved. These are
optimistic checks, not locks against arbitrary external filesystem writers. The publication lock covers saves, moves and deletes.

QLockFile leases stay at the conversation root by stable ID, so moves cannot
bypass another window's edit ownership. Leases prevent simultaneous UI editing
of a conversation. A short
publication lock serializes save revision checks and atomic replacement. Failed
publication does not advance the in-memory revision. Unsupported or malformed
data are preserved. Profiles have an independent lock and expected-value check;
only ID, display name and base URL are published. The feature uses the existing
Logistics preference-root mapping, without storing transcripts in `configuration/`.

Networking uses the already installed PySide6 QtNetwork module. All signals run
on the page's GUI thread; there are no feature-owned QThreads. Delta presentation
is coalesced at 50 ms and Markdown rendering at 80 ms. Requests have an inactivity
timeout and bounded response/frame sizes. HTTP redirects are not followed, TLS
errors are not bypassed, and remote error bodies are never displayed. JSON text/tool
responses are accepted when a server ignores streaming. Ordinary Chat rejects tool calls;
Code mode routes them through the project agent.
Transcript resource loading and automatic link navigation are disabled.

Enter sends only from the composer; Shift+Enter inserts a newline. Other fields
keep normal Qt key behavior. An active input-method preedit bypasses the send
handler to allow composition to finish.

The transcript and composer bind the shared `reading` font role, and transcript
code uses shared Markdown code styling. Grey user bubbles are right-aligned;
assistant replies are left-aligned. Only changed message bodies are rebuilt,
preserving earlier selections during streaming. Palette-aware icon controls expose
tooltips/accessibility names; Send becomes Stop while either request type is
active. The sidebar's three-dots menu owns conversation maintenance actions.
The built-in initial server is labelled `LM Studio (localhost default)`; saved
profile names remain user-owned. The token field is revealed explicitly.

Drafts debounce at 700 ms; active replies checkpoint at 1 s. Save failure cancels
generation, keeps the in-memory copy for export and vetoes closing unless the
user explicitly discards. `can_close()` settles persistence; `prepare_close()`
aborts networking, defers while a reply is live and releases the edit lease.
`idle` participates in the existing host close lifecycle. Destruction also
releases the retained lease. Feature disablement does not destroy active pages.

Boundaries: plain JSON data, in-memory-only tokens, text and pasted screenshot input, text output, manual
model context size, approximate budgeting and full-file autosaves. Search scans
local conversation files and is debounced, but is not a background indexed search.
Long transcripts retain native widgets per message; very large libraries may
warrant virtualization and a rebuildable search index later. No LM server is
installed/started. The normal footer uses the shared StatusLine; save errors keep
their separate wrapped recovery message.

Validation: `Python/tests/chat/test_lm_session.py` exercises replacement lease cleanup,
recovery, publication rollback and retained partial output without chat widgets.
`Python/tests/chat/test_lm.py` exercises schema/context/persistence/SSE;
`test_lm_ui.py` uses a local HTTP fixture and real Qt event loop for streaming,
timeouts, stop/close, failures, profiles and recovery. Real LM Studio and native
Windows/Linux behavior require separate smoke checks.

## Code mode and optional direct edits

Additive `mode`, `project_id` and boolean `allow_edits` fields preserve legacy version-one conversations.
Sidebar Chat/Code tabs filter the library and restore separate mode selections;
creation assigns the mode, and navigation cannot change an existing record’s mode.
Attachments are reviewed composer text, retained with the user's message rather
than hidden server-side context. Project registration lookup uses live IDE pages
when present, otherwise the existing ProjectStore; it never constructs an IDE page.
Editor text/selection snapshots are copied on the GUI thread before worker use.

AgentClient preserves the text client's start/busy/cancel/signal contract. It
owns the HTTP client and at most one ResultWorker, stays busy between tool rounds,
and emits completed only after networking/tools settle. Stop/close request
cooperative interruption and retain the owner until the worker finishes. Calls
are bounded to six rounds, 24 total and eight in one response. Tool results and
arguments persist in response metadata; token credentials remain session-only.
The token estimate includes tool schemas and cumulative result messages.

Tool paths must remain inside the resolved project root, respect configured
exclusions, and traverse no links. POSIX disk reads use directory-relative
no-follow opens; other platforms validate paths before opening. Regular UTF-8
files are limited to 256 KiB. Reads return at most 200 lines/10,000 characters;
searches cap directory traversal, bytes read and result count. No shell command,
executable loading or network tool exists. The model receives
plain data and cannot expand the tool set.

`allow_edits` defaults to false and is captured with the request; the checkbox is
unavailable during generation. Only enabled Code requests expose `edit_file`.
Editable reads use current disk text; read-only requests retain editor snapshots.
The edit tool requires a prior read version and a unique exact text replacement
in an existing UTF-8 file, bounded to 256 KiB. It retains original bytes as its
conflict baseline and uses the shared atomic text writer with expected bytes,
retaining permissions, BOM and line endings. The Git index is never changed.

`ui/project_edits.py` queues edit requests from the tool worker to the GUI thread.
It validates every matching live IDE buffer, refusing modified/stale/read-only
buffers and pending/failed autosaves before writing. The bounded write and buffer
publication run in the same GUI callback so typing cannot intervene. Successful
edits update each shared document through an undo edit block, advance its disk
snapshot and reset its modified flag. Cancellation is checked both in the worker
and the queued callback; completed saves remain on cancellation. Atomic writes
check disk bytes before staging and promotion; arbitrary external processes are
not transactional with the final rename. New files, deletes and renames are not
part of this tool. `test_lm_edits.py` covers editor synchronization/undo, pending
text/autosave conflicts, disk conflicts, BOM/CRLF, path boundaries, worker dispatch
and preserving staged plus unrelated unstaged text. HTTP fixtures exercise the
model's read/edit/continuation sequence and persisted toggle.

### Persisted changes for each response

`changes.py` generates unified patches from the text before the first successful
edit and after the last edit of a file. The tools retain these baselines only for
the request; assistant messages persist an optional `changes` list containing
`path`, `patch`, `added`, `removed` and optional boolean `undone`. Records validate at most 24 unique paths,
text patch bounds and nonnegative counts. No full snapshots are sent to the model
or added to the request context. Patches retain no-final-newline markers. Net-zero
edits disappear from the summary. A file changed by another writer after an AI
save cannot receive another edit during that turn, preventing that writer's
changes from entering the turn diff.

After every successful save, `ProjectEditDispatcher.changes_saved` publishes the
current list on the GUI thread. The page attaches it to the active assistant
message and immediately checkpoints before the next model request. Completion,
cancellation and failure preserve it independently of tool metadata. A checkpoint
failure stops generation with the existing export/recovery feedback; saved file
edits and in-memory patches remain available. A crash between a file save and its
conversation checkpoint can still lose that edit's history.

`ui/changes.py` owns the clickable file card and a lazy right-hand pane using
`features.git.ui.preview.Preview`, without repository commands or hunk mutation
controls. Selection resolves only saved message data; paths never trigger a disk
read. Conversation changes clear the pane, while streaming updates refresh the
selected response's saved patch. JSON exports, moves and forks retain the message
fields. Old records without `changes` show no card. `test_lm_changes.py` covers
aggregation, no-final-newline patches, validation, isolation from model context,
click-through viewer reuse, reopening, cancelled response persistence and failed
checkpoint recovery; the HTTP edit fixture verifies end-to-end saved patches.

### Guarded Undo

`undo.py` parses saved unified patches and reverse-applies them to current text
using unique exact post-edit hunk matches, including unchanged context and
no-final-newline markers. It permits line shifts and unrelated later text but
refuses changed/ambiguous context, malformed patches, overlapping/reordered hunks
and context-free insertions into nonempty files. There is no fuzz or full-file
reset. Matching is bounded to the project tool's 256 KiB file limit and stops
after finding a second candidate. Existing patch-only records are supported.

The card's Undo signal resolves the selected assistant message, its original
registered project ID and captured root. A changed/missing registration refuses
the operation; current picker selection cannot retarget historical changes.
`ProjectEditDispatcher.undo_changes` preflights all pending files through the
project path/exclusion policy, reverse patch, file permissions and live editor
checks. Only then does it publish guarded atomic writes on the GUI thread,
revalidating each file's path, editor state and expected disk bytes at promotion.
Open buffers receive the same undoable publication used for model edits. The
Git index is untouched. Generation and connection requests disable Undo.

Each saved file gets `undone=true` and an immediate conversation checkpoint;
retries skip it and keep the original patch as history. A conflict during
preflight changes no files. External writes can still race after preflight, so a
late conflict or checkpoint failure stops remaining writes and reports partial
progress without attempting a destructive rollback. In-memory progress survives
publication errors for retry/export; a crash between file save and checkpoint
can leave disk ahead of history, in which case strict patch matching prevents
blind reapplication. `test_lm_undo.py` covers multi-hunk shifts, conflicts,
ambiguity, blank files/newline markers, card clicks/reopening, staged data,
pending/live buffers, original project identity, symlinks, BOM/CRLF/permissions,
racing writers and checkpoint failure with retry.

Project-tool unit tests cover boundaries, binary/large files, snapshots and
context budgets. HTTP/Qt fixtures cover fragmented SSE and JSON tool calls,
continuation messages, unknown/outside-scope calls, call limits, persistence,
attachments and worker cancellation during close.

## Screenshot persistence

Optional `draft_images` and user-message `images` fields hold self-contained PNG
records (UUID, MIME, base64 bytes, width/height). Validation checks encoding, PNG
header, dimensions and per-image/count limits before native decoding. Clipboard
paste routes image MIME data through Composer; ordinary text paste stays native.
Draft publication/rollback, tab switching, close recovery and history all retain
images. Embedded records make folder moves, forks and JSON export portable
without file references or sidecar lifecycle. Markdown export uses data URLs.

Requests preserve string content for text-only messages and emit text/image_url
parts for screenshots. Whole-turn selection includes historical images. Both
request-building and agent continuation budgeting reserve vision tokens instead
of counting base64 as text. Native screenshot widgets render only validated local
records; arbitrary Markdown resources remain blocked.

## Further reading

- [LM Chat integration](lm.md)

## Mobile ownership

`mobile/storage.py`, `mobile/transport.py`, `mobile/presentation.py` and `mobile/ui.py` own mobile chat. The mobile host composes the view and supplies application presentation utilities. `streaming.py` owns SSE decoding shared by both transports; Qt networking stays in `transport.py`. Mobile retains its one-choice, text-only, 64 KiB event, 256 KiB response and timeout/cancellation limits.

`ChatController.state` owns the current conversation reference, request activity,
selection suppression and inventory refresh task. `ChatController.transcript` owns
the WebView render epoch, task and incremental baseline. Controls remain directly
on the controller; `ConversationSession` still owns generation publication and
rollback. Chat UI methods read these records directly. Existing app `chat_*`
accessors forward to the same records without copying state. Host capabilities
are read-only references that follow the application's current services.

## Mobile source manifest

`../../mobile_sources.json` declares this feature's selected portable/mobile sources. Update it when adding an imported module. The build tool aggregates and checks the allowlists without starting desktop registration.

## Injected desktop adapters

`Store(..., lock_factory=...)` accepts a path-to-lock factory. The default
`ui/leases.py` adapter constructs Qt locks lazily. Storage still chooses lock
names, nonblocking acquisition, stale-lock handling and conflict errors; leases
must implement `setStaleLockTime`, `tryLock`, `unlock` and `isLocked` where used.
`LMPage(..., project_context=...)` optionally accepts an object with `projects()`
and `buffers(project)`. Default context still uses the lazy IDE integration;
injected hosts avoid global IDE widget discovery. Conversation formats and
session ownership are unchanged.

## Desktop project attachments

`ui/attachments.py` owns project-file/IDE-selection picking, containment checks and
bounded publication into the composer. `LMPage.attachments` composes it through
`AttachmentHost`; the page retains compatibility entry points for menus and callers.
Conversation persistence, transport and screenshot records retain their existing
owners. File dialogs use the page as native parent. Cancellation publishes nothing;
project exclusions and the 64 KiB draft limit still apply. `test_lm_ui.py` exercises
attachment selection, excluded files and persisted project choice.

## Shared desktop and mobile generation

Both presentations use `GenerationCoordinator` and `ConversationSession` for
publish-before-dispatch, rollback and response transitions. Desktop project tools
are injected through `execution.desktop.project_tools`; portable generation no
longer imports the desktop tool implementation. Mobile wraps its client in
`execution.mobile.MobileGenerationTransport` and drains queued fragments on the
owning event loop. The shared session remains the record/dirty/response owner.

Capture `session.response_token` for callbacks and pass it to `append_delta` and
`complete_response`. It identifies the conversation generation and active response;
late fragments or terminal callbacks from a replaced response are rejected.
Mobile additionally checks the active host/conversation before queueing fragments,
and `retire` cancels and awaits its worker before clearing pending text. Cancellation
and failure keep their distinct terminal states. A new draft typed while an answer
streams must survive terminal publication; callers must not clear it again.

Credentials remain dispatch-only. Publication failure prevents transport start
and restores the editable record; failed transport startup retains the published
user turn and records failure. Preserve lease/revision checks and surface a
secondary save failure for retry/export. Focused coverage is in
`test_lm_session`, `test_lm_generation` and mobile chat tests; native synthetic
stream/draft checks validate presentation without a real server account.

## Desktop menu assembly

`ui/menus.py` assembles the conversation menu bar from the page's existing actions
and callbacks. The page retains conversation state, persistence, control enablement
and signal ownership; menu assembly does not create a second session owner.

## Stream framing boundary

`streaming.StreamDecoder` consumes shared bounded data-only SSE framing. The LM
feature retains `[DONE]`, JSON validation, choices, tool fragments, response limits,
finish reasons and usage. It preserves partial text on later record failures and
keeps desktop/mobile response-policy differences in their transports.

The shared decoder bounds and accumulates plain-text `reasoning` and
`reasoning_content` separately from answer text. The desktop transport emits
`reasoning_delta` for SSE and JSON replies, preserving received reasoning on
stop/failure; `AgentClient` includes it in the aggregate response size limit.
`ConversationSession.append_reasoning` uses the same response ownership guard as
answer deltas. Completion records `elapsed_seconds` using a monotonic clock from
response publication through all tool rounds. Optional reasoning and timing
fields are validated and saved without changing the record version; request
building uses answer content only.

Desktop bubbles use an in-flow, selectable reasoning browser under the activity
header. The header shows live wall-clock elapsed time until monotonic completion
timing is available; its dropdown exists only when reasoning text was returned.
It opens during reasoning and folds on answer text unless manually toggled.
Legacy records retain a plain Response/status header. Mobile consumes the shared
decoder without a reasoning UI. Fixture tests in `test_lm_streaming`,
`test_lm_session` and `test_lm_ui` cover separate deltas, limits, persistence,
follow-up context exclusion, JSON fallback and inline expansion.


## Desktop appearance refreshes

`ui/conversation_view.MessageBrowser.refresh_font` compares the effective reading
font, embedded-code family/size and application palette cache key before forcing
another Markdown import. Theme and shared-styling notifications for the same
appearance therefore render each message once. Unrelated font roles do not import
message documents. Actual content/stream updates still use `set_source`, retaining
cursor selection through imports. Local font/chrome stylesheets are set only when
their text changes. `test_lm_appearance.py` covers duplicate signals, reading/code
changes, selection retention and subsequent content updates.

The desktop composer is a bottom-aligned sibling overlay on the full-height
transcript in `layout.py`'s `message_surface` grid. Its right-hand grid column
reserves the transcript scrollbar's width. `LMPage.fit_composer` measures native
wrapped block heights and limits the dock to about half the message surface,
including its toolbar and attachment previews. Dock resize/layout events update
the transcript's bottom layout margin; the last bubble can scroll fully above
the composer while the draft stays in place during history scrolling.
The existing model selector is hosted in the composer's bottom toolbar and stays
disabled during generation. User bubble palettes derive from the theme's accent
(`Link`) color with contrasting text. `test_lm_appearance` covers the overlay,
bottom clearance, scrollbar access, resizing and live theme changes.

`ui/answer_speech.py` owns a lazy, single-answer read-aloud session for each
desktop transcript. It uses commonUtils' `SpeechSession` and `QtSpeechEngine`
with the installed engine's default voice and normal speed, without the reader's
settings panel. Only the rendered answer document is spoken. Repeated clicks
stop playback, another answer replaces it, and hide/close, conversation changes
or message removal stop queued utterances. The engine is disposed with the view.
`test_lm_speech.py` uses a silent adapter to verify toggling, chunking, stale
completion rejection, default parameters, unavailable voices and view lifetime.
