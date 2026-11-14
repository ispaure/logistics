# LM feature implementation

## Try a desktop composer change

In desktop **LM Chat**, paste 100 unsent lines into a new conversation. Raise the height fraction in `Python/features/lm/ui/page.py:LMPage.fit_composer` from half to 60%, preserving the minimum, controls and transcript padding. Update the height expectations in `test_multiline_draft_grows_to_half_the_chat_area_then_scrolls_and_shrinks`. From the checkout root, expect the long draft to scroll at the new cap and a one-line draft to shrink the dock. No server is needed.

```sh
python3 dev.py test desktop --exact-file Python/tests/chat/test_lm_appearance.py
```

## Find the desktop owner

`register` lazily exposes `lm.chat`. Under `Python/features/lm/`, `ui/page.py` and `ui/composer.py` own input, `ui/conversation_*.py` owns history and presentation, `ui/profiles.py` owns server settings, and `domain.py`, `storage.py` and `session.py` own records and leases. `ui/attachments.py` checks containment, exclusions and the 64 KiB draft cap before inserting reviewable attachments. `ui/ide_context.py` snapshots editors on the GUI thread.

## Mobile ownership

`ChatController.show_chat_configuration` opens `mobile/chat_settings.py:ChatSettingsPanel` from Chat or Settings and returns to the originating destination. `mobile/ui.py` owns workspace controls, `presentation.py` the transcript and `laptop.py` reserved-region layout. Retain draft and transcript across resizing. [Mobile server setup](lm.md#mobile-server-setup)

## Shared desktop and mobile generation

`GenerationCoordinator` publishes the pending user turn before dispatch. Publication failure restores editable state. Startup failure retains the turn and records failure. Keys stay in memory. Pass `session.response_token` to delta and terminal callbacks to reject stale responses. Retirement cancels and awaits workers. Preserve partial replies and any new draft, and surface save failures for retry/export.

`streaming.StreamDecoder` owns bounded SSE/JSON response policy, tool fragments and usage. Reasoning is separately bounded, saved with optional elapsed timing in version-one records and excluded from follow-up context. Desktop renders expandable reasoning; mobile shares the decoder.

## Code mode and optional direct edits

Version-one records accept additive `mode`, `project_id` and `allow_edits`. Project tools enforce contained, nonlinked paths, exclusions, regular UTF-8 files (256 KiB), bounded reads/search and six rounds/24 calls. Opt-in edits require a prior read revision and unique exact replacement. `ui/project_edits.py` checks live buffers and pending autosaves on the GUI thread, then publishes through the expected-byte writer and updates buffers with undo. Preserve permissions, BOM, line endings and Git index. Stop retains committed writes.

### Persisted changes for each response

`changes.py` tracks net patches from each file's first baseline to its last saved edit. Checkpoint the assistant message after each write. A failed checkpoint stops generation and retains edits and in-memory patches for export or retry.

### Guarded Undo

`undo.py` reverse-applies unique exact hunks against the original project registration. Preflight every file, then recheck each write. Conflicts or checkpoint failures stop the remaining writes. Persist `undone=true` per file so retry skips completed entries. A crash can leave disk ahead of the checkpoint; strict matching guards retry.

## Choose a focused check

Use `python3 dev.py test desktop --exact-file` with paths under `Python/tests/chat/`. Select `test_lm_session.py` or `test_lm_generation.py` for publication, `test_lm_streaming.py` for decoding, or `test_lm_edits.py`, `test_lm_changes.py` and `test_lm_undo.py` for writes. `test_lm_ui.py` includes loopback HTTP. See [LM Chat integration](lm.md) for mobile and record checks.
