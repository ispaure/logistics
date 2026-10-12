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
[user behavior](../../Python/features/lm/user_docs/README.md). Future agent/tool
integration would require a separate execution and permission contract; current
transport rejects tool calls and provides no filesystem/shell tools.
