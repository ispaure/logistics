# Transfer planning, review and execution

Desktop **Workspaces → Cloud → Pull** follows `ui_contributions.py:_get_actions` through `actions.py` to `transfers/workflow.py:sync_transfer`. Mobile starts in `transfers/mobile/review_ui.py`.

## Follow a transfer

1. Build a platform plan with captured credentials, mapping and options. Mobile validates an immutable `CopyMapping`.
2. Interactive `TransferService.review` compares read-only. Full approval compares again and asks again if changed. Incomplete approval cancels and retires comparison before execution.
3. `execute` consumes approval once and checks the binding. Retrying an interactive execution requires fresh review.
4. Keep review validity (mapping/record state) separate from execution access (credential lifetime). Cancellation keeps committed writes.

For a readable mobile Pull, the bridge validates the destination root and
checks the paths rclone lists or writes during the sync. It skips destination
links when listing and rejects writes that would use a linked path. LocalCrypt
and Push keep their preflight checks. An interactive review can still run a
read-only comparison before execution.

Android Pulls to a public FAT-family volume stage up to ten files in parallel
with preallocation disabled. Writers reserve the reported size of each staged
file against shared free space with a 16 MiB margin. They can wait for an
existing stage to finish when space is tight. Out-of-space errors end the
attempt. Readable SD Pulls accept size matches with a modification-time
difference of up to one second to account for rounded card timestamps.
Comparison otherwise uses rclone's standard equality checks and concurrency.

## Completion notifications

Logistics opts desktop browser copy, move and export, integrated rclone sync,
and staged downloads into completion notices. Mobile managed sync and selected
downloads enter through `TransferExecution.run`. Desktop previews and terminal
launches outside the integrated progress window have their own progress and
completion handling. Mobile admits one managed transfer writer at a time.

For another user-started transfer, allocate one `start_transfer_notice()` from
`services.transfer_notifications` at execution admission. Pass the verified
terminal outcome to `transfer_notice` on the UI thread after the worker retires.
Use a fixed, human-facing name for the details destination. Mark the result
observed if its progress view is visible in the foreground. Keep cancellation
feedback in the progress UI. The 30-second threshold allows time to navigate
away and filters routine short copies and immediate failures. Keep names, paths,
errors and credentials in the protected details view. Revalidate access and
job ownership before opening details.

Desktop publishes to the existing notification center and toast. Workspace
actions retains each unread job if the system tray cannot show it. Native tray
activation can open the Workspace actions destination. Qt does not report
whether the OS displayed an accepted tray message. Mobile keeps a bounded
in-memory queue for foreground delivery, including results deferred while the
OS or the app's settings prevent background delivery. The adapters schedule
only local notices. They do not start, extend or resurrect transfer execution.
A terminated process can't publish a new terminal event. The download
recovery journal continues to own resumable work.

## Download selected items

Desktop **Download locally…** runs `transfers/remote_download.py` under the browser's
credential grant. Mobile starts in `mobile/remote_downloads.py` and uses the
existing Transfers execution, cancellation and progress controls. Small files,
directories and explicitly approved full restarts use the staged CLI or native
rclone copy. Folder downloads include empty directories. Completion refreshes
the published parent and preserves the retained browser selection.

Desktop SMB uses this full-copy path for every selected item. A staged copy
publishes to the chosen local destination only after the worker rechecks the
credential grant. The remote browser exposes download and export operations.

For files of at least 8 MiB, `transfers/download_recovery.py` records the job
ID, selection, physical destination, parent and partial inode, source version,
logical offset, stored-prefix SHA-256 and publication state. The worker syncs
each range before advancing the atomic journal. An inode-bound reservation
recovers a stage created just before a crash. An unrelated replacement is
preserved. Workspace sync filters out the reserved partial names. Restart verifies the local
prefix, trims an uncommitted tail and checks space for the remainder. A
publishing job verifies the complete stage or the exclusively renamed target
before retiring its journal. A destination lock serializes competing workers.

Desktop binds journals to the active configuration and uses the credential ZIP
cipher for session-only accounts or the existing credential-derived cipher for
saved settings. The mobile bridge uses credential-password encryption for
session jobs and device-protected encryption for saved credentials. The queue
is loaded only through a current grant. The remote File menu on desktop and
the Transfers screen on mobile reopen or discard a selected job.

Plain HTTP recovery requires a strong ETag, identity encoding and an exact
conditional range response. The desktop adapter also supports a local alias,
crypt over supported range backends and selected cloud files with a usable
checksum. On mobile, `download_range.go` binds ordinary bytes to a provider
checksum. Crypt reads bind to the file header and authenticate each complete
64 KiB block and the final short block. For a matching LocalCrypt destination
the worker persists those original ciphertext bytes, including the header
once. A transfer that needs fresh encryption offers the existing full copy.

The recovery regression tests cover changed sources and partials, disk space,
writer contention, stage creation, explicit restart approval, repeated interruption
and both sides of publication. The
host acceptance probe runs workers in separate processes against generated
loopback HTTP or TLS WebDAV data. It measures server payload bytes and compares
the final digest with the independent generator. Run from the repository root
with the desktop environment, `PYTHONPATH=Python:.` and the checkout's pinned
Go, desktop rclone and mobile environment installed.

```sh
.venv/bin/python -m mobile_build.validation.download_recovery_probe --mode desktop-http --receipt tmp/test-results/recovery/http.json
.venv/bin/python -m mobile_build.validation.download_recovery_probe --mode native-crypt --receipt tmp/test-results/recovery/crypt.json
```

Run the Android acceptance on a Manager-owned disposable emulator from the same
checkout. It drives the destination picker and Transfers controls and force-stops
the QA app at 16 MiB. The ranged server checks each resumed request against the
remaining bytes. The probe verifies the final plaintext SHA-256 for a password
session, saved credentials and a matching LocalCrypt destination. It also compares
the stored LocalCrypt ciphertext with the desktop rclone fixture, records Android
KeyInfo for the vault key and declines the byte-zero prompt on a source without
a checksum. The QA build trusts a generated loopback certificate in its private
app directory.

```sh
mobile_build/.venv/bin/python -m mobile_build.validation.document_storage_tools android --probe download-recovery --output tmp/test-results/android-recovery
```

The probe checks free capacity and removes its managed scratch directory.
The default fixture is 64 MiB plus 137 bytes. Use `--size` for larger runs.

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
