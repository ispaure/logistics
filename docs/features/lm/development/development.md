# LM feature implementation

LM Chat sends conversations to a configured model server and keeps them
locally. Desktop also offers Code mode for registered projects. Android and
iOS support server chat and optional platform models. See the
[LM guides](../lm.md) for setup and usage.

## Try a desktop composer change

In the desktop sidebar, open **LM Chat** and start a new Chat conversation.
Paste several lines of synthetic text into the message field. Paste roughly
100 lines to see the composer stop growing and scroll internally. Leave the
draft unsent. This exercise needs no model server.

For a local experiment, let the composer dock occupy about 60% of the message
area instead of half. In
`Python/features/lm/ui/page.py:LMPage.fit_composer`, change the fraction used
in the `maximum` calculation. Keep its minimum height, the deduction for the
dock controls and the transcript's scroll padding. Update the two height-ratio
expectations in
`test_multiline_draft_grows_to_half_the_chat_area_then_scrolls_and_shrinks`.
Relaunch and check the taller cap, then resize the window and replace the
draft with one line. The dock should shrink again.

From the checkout root with the [desktop environment](../../../development/setup/getting-started.md)
set up, run:

```sh
python3 dev.py test desktop --exact-file Python/tests/chat/test_lm_appearance.py
```

Expect six passing tests. The long draft scrolls at the revised cap and the
short draft returns to its normal height. The remaining cases check readable
themes, model selection and space below the last message.

## Find the desktop owner

`Python/features/lm/__init__.py:register` declares the `lm.chat` page and chat
defaults. Its factory imports `LMPage` lazily. Registration and construction
perform no network requests. Start under `Python/features/lm/`.

| Change | Owner |
| --- | --- |
| Page lifecycle, draft controls and resize | `ui/page.py`, `ui/layout.py`, `ui/composer.py` |
| Menus, conversation actions and navigation | `ui/menus.py`, `ui/conversation_actions.py`, `ui/conversation_tree.py`, `ui/mode_tabs.py` |
| Transcript, appearance and per-answer speech | `ui/conversation_view.py`, `ui/answer_speech.py` |
| Server profiles and validation | `ui/profiles.py`, `configuration.py` |
| Saved data, revisions and leases | `domain.py`, `storage.py`, `session.py` |
| Qt transport, project tools and requests | `transport.py`, `execution/desktop.py`, `generation.py`, `agent.py` |

Import desktop presentation from `features.lm.ui`. Mobile reuses portable
domain, session and request code with its own transport and persistence
adapters. For version-one records, screenshots and mobile provider
configuration, see [LM Chat integration](lm.md).

## Mobile ownership

The host creates `ChatController` on demand. Enable LM Chat to expose **Chat**
in mobile navigation. **Chat → Model & server settings** and **Settings →
LM Chat → Server & generation settings** route through
`ChatController.show_chat_configuration`. `mobile/chat_settings.py:ChatSettingsPanel`
retains the originating destination. Opening from Settings can initialize the
controller without presenting Chat. Back or Save returns to the origin.

`mobile/ui.py` owns the conversation workspace; `mobile/presentation.py`
renders the transcript. `mobile/laptop.py` allocates retained controls around
horizontal UIKit reserved regions. Draft and transcript stay mounted during
layout changes. Typography follows the shared Markdown size, converted at
the native input boundary. The history drawer groups recycled rows by
last-updated month and validates row identity on disclosure. See the
[mobile integration contract](lm.md#mobile-server-setup) for settings/profile
behavior and native checks.

## Desktop project attachments

`ui/attachments.py` applies project containment, exclusions and the 64 KiB
draft limit before inserting selected files or IDE selections into the
reviewable composer text. `ui/ide_context.py` copies active editor snapshots
on the GUI thread and can use project registrations without constructing an
IDE page. `test_lm_ui.py` checks exclusions, byte limits, selection attachment
and project choice.


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

## Choose a focused check

From the repository root, use `python3 dev.py test desktop --exact-file`
with the path under `Python/tests/chat/`. Choose `test_lm_session.py` or
`test_lm_generation.py` for publication and cancellation, `test_lm_streaming.py`
for stream decoding, and `test_lm_edits.py`, `test_lm_changes.py` or
`test_lm_undo.py` for the relevant project write path. `test_lm_ui.py` combines
local widget fixtures with loopback HTTP fixtures that require permission to
bind a local socket. Mobile ownership and provider checks are linked from
[LM Chat integration](lm.md).
