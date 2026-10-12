# LM feature implementation

The feature's lazy `register()` contributes `lm.chat`, the `lm` rail glyph and
typed chat defaults. Registration/page construction never make network requests.
The [user guide](user_docs/README.md) describes available workflows and limits.

| Module | Ownership |
| --- | --- |
| `domain.py` | Version-one records, validation, generation defaults, context budgeting |
| `configuration.py` | Central settings validation |
| `storage.py` | Platform LM root, nested folders, profiles, edit leases, optimistic revisions, export |
| `transport.py` | Qt asynchronous HTTP, bounded SSE decoding, request cancellation |
| `page.py` | Folder tree, conversation selection, Enter/Shift+Enter composer, generation lifecycle, profile editor |
| `conversation_view.py` | Incremental native Markdown bubbles and bounded message sizing |
| `icons.py` | Palette-aware toolbar and Send/Stop glyphs |

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
errors are not bypassed, and remote error bodies are never displayed. JSON text
responses are accepted when a server ignores streaming. Tool calls are rejected.
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

Boundaries: plain JSON data, in-memory-only tokens, text-only input/output, manual
model context size, approximate budgeting and full-file autosaves. Search scans
local conversation files and is debounced, but is not a background indexed search.
Long transcripts retain native widgets per message; very large libraries may
warrant virtualization and a rebuildable search index later. No LM server is
installed/started. The normal footer uses the shared StatusLine; save errors keep
their separate wrapped recovery message.

Validation: `Python/tests/test_lm.py` exercises schema/context/persistence/SSE;
`test_lm_ui.py` uses a local HTTP fixture and real Qt event loop for streaming,
timeouts, stop/close, failures, profiles and recovery. Real LM Studio and native
Windows/Linux behavior require separate smoke checks.
