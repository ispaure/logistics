# Transfer planning, review and execution

Desktop **Workspaces → Cloud → Pull** follows `ui_contributions.py:_get_actions` through `actions.py` to `transfers/workflow.py:sync_transfer`. Mobile starts in `transfers/mobile/review_ui.py`.

## Follow a transfer

1. Build a platform plan with captured credentials, mapping and options. Mobile validates an immutable `CopyMapping`.
2. Interactive `TransferService.review` compares read-only. Full approval compares again and asks again if changed. Incomplete approval cancels and retires comparison before execution.
3. `execute` consumes approval once, checks the binding and runs mandatory platform preflight. Programmatic `run` also preflights. Retrying an interactive execution requires fresh review.
4. Keep review validity (mapping/record state) separate from execution access (credential lifetime). Cancellation keeps committed writes.

## Download selected items

Desktop **Download locally…** runs `transfers/remote_download.py` under the browser's
credential grant. It uses rclone `copyto` for files and `copy` for folders,
including empty directories. The worker stages beside the chosen destination
and publishes with an exclusive rename after checking cancellation and access.
The desktop Pull progress view shows rclone transfer statistics and reports
completion after publication.
The desktop browser relists tabs at the published item's parent. Its filesystem
model retains the existing selection and navigation.

On mobile, `mobile/remote_downloads.py` captures path, kind and generation.
Go `download_sync.go` stages file Copy or folder Sync in independent storage,
encrypted for LocalCrypt. Python publishes without clobber and retires staging
on cancel or failure. The destination picker tells the mobile browser owner
to refresh retained listings of the same parent after completion. Selected
downloads leave mirror records unchanged. Check `test_remote_downloads.py`
and native `TestDownload*`.

## Review and progress presentation

Portable `transfers/{service,review,presentation}.py` own review and bounded display models. Desktop uses Qt. Mobile setup and review in `transfers/mobile/surface.py` use offline `assets/surface.*`, escaped paths, private WebViews, token/command/revision checks and 30 rows per page. Approve only a rendered current snapshot. Retire scans on close and redact private progress on revocation.

Replace a stalled setup or review WebView once, then use `native_fallback.py`
with the same action guards. The progress page uses these native controls from
its first presentation, independently of the tab progress ring. Coalesce
ordinary progress, retain terminal snapshots and show verification separately
from completion. Unknown totals stay indeterminate. Browsing retains jobs.
Stop binds confirmation to the active epoch.

## Native owners

| Change | Owner under `transfers/mobile/` |
| --- | --- |
| Schema and outcomes | `models.py`, `records.py` |
| Mapping and plan admission | `planning.py`, `plan.py` |
| Writer locks, preflight and save/verify order | `jobs.py:MirrorJobs` |
| Bridge polling and presentation lifecycle | `transport.py`, `execution.py`, `review_ui.py` |

Read schema 3 and atomically save schema 4. Validate the record key, mapping, connection identity and distinct cipher identity; retain the old catalogue on invalid state. Keep dictionary and tuple compatibility for programmatic clients. Validate legacy outcomes before converting to `TransferOutcome`; conflicts stay incomplete.

## Find desktop transfer controls

Start at `transfers/ui/progress.py:transfer_presentation` for the dry-run labels and removal counters used by desktop transfers. `transfers/progress.py:RcloneProgressParser` converts stats to shared `ProcessUpdate`. commonUtils `ui/tasks/process_transfer_progress.py` renders the transfer table. `ui/tasks/process_progress.py` owns the bar, logs, Cancel and Close. The runner supplies the exit result. `desktop/folder_actions.py:FolderActionsPage` owns tabs and docking. Setup and review live in `transfers/ui/`.

Old `transfers.sync._watch_transfer` and `transfers.progress.add_removal_statistics` delegate with `FutureWarning`. Use `transfers.ui.progress` for new calls. `rclone_sync` preserves legacy results. `launch.py:LaunchMode` distinguishes preview, wait, GUI and terminal. Only `SUCCEEDED` means completed; private sessions without GUI run synchronously to protect secrets.

## Python–Go boundary

`mobile/bridge_protocol.py` validates wire envelopes, sizes and outcomes; `CloudClient` frees native replies before validation. Go `protocol.go` handles admission, `requests.go` dispatches and `operation_scope.go` owns cancellation/publication. Keep intentional Python/native size differences in `mobile_build/rclone_bridge/protocol_contract.json`.

## Mobile transfer appearance

Edit setup and review light/dark defaults and older-engine fallback pairs in
`transfers/assets/surface.css`. E Ink has overrides. `surface.py` injects
palette roles through `services.appearance_palette.css_variables()`. The
native progress controls use the host appearance.
Use `rclone-transfer` to check rendering and selected crypt downloads.

## Mobile sync shortcut layout

`mobile/transfer_status.py` mounts the 48-point/dp root shortcut. Nested readers hide it. Use `document_storage_tools --probe sync-status` for bounds, rotation and reader animation retirement. [Mobile commands](../../../development/build-release/mobile-launchers.md)

## Checks for a change

```sh
python3 dev.py test desktop --exact-file Python/tests/resources/test_transfer_adapters.py
python3 dev.py test mobile --exact-file mobile_build/tests/transfers/test_mirror_ui.py
python3 dev.py test mobile --exact-file mobile_build/tests/tooling/test_bridge_protocol.py
```

Expect captured-option, revocation, incomplete-approval and wire-validation checks. Mobile Pull can replace an open file while retaining its draft; later save detects conflict. Push requires save or close. Use Go fixtures for engine behavior and the managed native probes for rendering.
