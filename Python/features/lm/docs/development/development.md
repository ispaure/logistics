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
| `agent.py` | Read-only tool rounds, context/call limits and cooperative worker ownership |
| `project_tools.py` | Project path/exclusion checks, bounded file listing, text search and line reads |
| `session.py` | Conversation record, edit lease, dirty state, publication and streaming response transitions; no widget dependencies |
| `ui/page.py` | Navigation, UI value collection, transport dispatch, GUI-thread timers, save feedback and close prompts |
| `ui/layout.py` | Widget construction and layout, without conversation state ownership |
| `ui/composer.py`, `ui/mode_tabs.py` | Enter/Shift+Enter, screenshot paste/drop, sampling controls and Chat/Code tabs |
| `ui/profiles.py` | Identity-preserving server profile editor |
| `ui/ide_context.py` | Lazy project registration lookup and GUI-thread editor snapshots |
| `ui/conversation_tree.py` | Tree drag requests; storage operations stay outside the widget |
| `ui/conversation_view.py` | Incremental native Markdown bubbles and bounded message sizing |
| `screenshots.py` | Bounded inline PNG records and image context reserve |
| `ui/image_view.py` | Native previews and screenshot viewer |
| `ui/icons.py` | Palette-aware toolbar and Send/Stop glyphs |

Start a desktop UI change at `ui/page.py`, record/lease changes at `session.py`,
saved-file contracts at `storage.py`, and request construction at `domain.py`.
Registration imports `ui/page.py` lazily. The old root-level presentation modules
remain compatibility imports of the same classes/functions; new code should use
`features.lm.ui`. Request/agent adapters remain at the feature root; they do not
own widgets. Mobile continues using the selected portable domain/screenshot code,
without importing the desktop package.

`ConversationSession` receives a store and owns the active record, lease, dirty
flag and streaming response. It acquires/loads or publishes a replacement before
releasing the prior lease. Recovery marks streaming records interrupted only
after acquiring their lease. Response insertion and draft clearing publish before
network dispatch; failure restores the record and leaves it dirty for retry.
Completion clears active response ownership while retaining partial text, even
when publication fails. Storage errors propagate to the page for recovery UI.

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
preserves the source. Source retirement failure removes the new copy; if rollback
also fails, both copies remain recoverable and duplicate detection blocks editing
until resolved. The publication lock covers saves, moves and deletes.

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
Code mode routes them through the read-only agent.
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

Validation: `Python/tests/test_lm_session.py` exercises replacement lease cleanup,
recovery, publication rollback and retained partial output without chat widgets.
`Python/tests/test_lm.py` exercises schema/context/persistence/SSE;
`test_lm_ui.py` uses a local HTTP fixture and real Qt event loop for streaming,
timeouts, stop/close, failures, profiles and recovery. Real LM Studio and native
Windows/Linux behavior require separate smoke checks.

## Read-only Code mode

Additive `mode` and `project_id` fields preserve legacy version-one conversations.
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
searches cap directory traversal, bytes read and result count. No file mutation,
shell command, executable loading or network tool exists. The model receives
plain data and cannot expand the tool set.

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
