# Transfer planning, review and execution

Interactive Push/Pull uses `TransferService.review` then `execute`. Programmatic
callers use `run` explicitly. Both use the captured platform plan and mandatory
execution preflight. Credential loading and persistence are described in
[credential lifetime](credentials.md).

## Follow a transfer

1. Desktop `transfers/workflow.py` captures a `DesktopTransferRequest`; native
   `transfers/mobile/review_ui.py` captures a `NativeTransferRequest`.
2. The platform `build_plan` captures credentials, options and destination. Native
   plans copy the proposal into a validated immutable `CopyMapping` so later edits
   to a caller's dictionary cannot redirect an approved transfer.
3. `ReviewSession` starts the read-only comparison. Full approval runs a fresh
   comparison; changed results require another decision. Explicit incomplete
   approval cancels comparison and waits for retirement before execution.
4. `TransferService.execute` consumes one approval, checks its binding and invokes
   the plan. Reusing approval, including after preflight failure, requires review.
5. The platform preflight validates paths, connection identity and ciphertext as
   applicable. Engine execution retains access/cancellation checks until retirement.
   Cancellation preserves changes already completed at the destination.

The review's `valid` binding includes mapping/record state. Its execution `active`
binding tracks access lifetime without rejecting legitimate record saves by the
transfer itself. Do not merge these checks.

## Native owners

| Responsibility | Owner under `transfers/mobile/` |
| --- | --- |
| Mapping schema, identity validation and named outcomes | `models.py` |
| Bounded JSON restore, schema-3 compatibility, atomic schema-4 saves and record comparison | `records.py:CopyRecords` |
| Resolve Pull/Push proposals without mutation | `planning.py:CopyPlanner` |
| Locking, destination admission, ciphertext preflight, save/execute/verify ordering and deletion | `jobs.py:MirrorJobs` |
| Native request, progress polling and monitor retirement | `transport.py:sync_copy` |
| Capture immutable request, comparison and execution binding | `plan.py` |
| Review controls and polling | `review_ui.py:TransferReviewDialog` |
| Review navigation/controller effects | `review_ui.py:MobileReviewPresentation` |
| Writer admission, worker retirement and progress delivery | `execution.py:TransferExecution` |

Review dialog callbacks are retired when the dialog closes. A late confirmation
cannot rebind cancellation or revive controls, and navigation failure still releases
the controller's busy/cancellation fields after comparison retirement.

`MirrorJobs` remains the compatibility API for mapping dictionaries. `CopyMapping`
validates the exact persisted field set; no saved-data schema changes are needed.
Saving checks the same 16-copy limit as restoration and requires each in-memory
record key to match its mapping identifier. Invalid catalogues are rejected before
publication, preserving the last readable record file.
Its connection `identity` binds the remote configuration/account; `cipher_identity`
binds crypt paths to cipher settings. `prefix` is the remote subtree (encoded for
ciphertext copies), while `target` is the local display/folder name.

`PullResult` and `CreatedCopy` name existing tuple fields while retaining tuple
compatibility. Reviewed plans produce `TransferOutcome`; presentation also accepts
legacy programmatic counts and tuples through a validating conversion. Invalid
counts, mismatched directions and malformed outcomes cannot publish success.
Completion messages are prepared before publishing the success flag, so a failed
formatter cannot leave a failed result marked complete.
A legacy or named conflict result remains incomplete: it cannot show 100%, mark
verified success or trigger the successful-transfer notification timeout.

## Desktop launch contract

`transfers/sync.py:rclone_sync` preserves the existing preview/bool interface.
It performs push preflight before `_run_sync`. That compatibility boundary converts
`_execute_sync`'s named `SyncOutcome` back to the historical result shape.

`transfers/launch.py:LaunchMode` makes preview, synchronous wait, integrated GUI and
terminal execution explicit after normalization of legacy flags. `SyncState.STARTED`
means a GUI/terminal launch was accepted; only `SUCCEEDED` means execution completed
successfully. The integrated window owns the eventual exit result. A private
session launched without a usable GUI runs synchronously to keep secrets out of
terminal command strings and the global environment.

`transfer_concurrency` names the existing source-path convention: paths containing
`-VM`, including parent directories, use one transfer; other paths use ten. This
refactor preserves that behavior rather than introducing a new preference.

## Python–Go boundary

`mobile/bridge_protocol.py` declares action names, envelope validation, request
limits, typed mirror-info/progress wrappers and validation for common result shapes.
`CloudClient` frees each non-null native response before validating its result.
Malformed progress, identities and file counts are rejected at the boundary.

`mobile_build/rclone_bridge/protocol_contract.json` is the shared synthetic fixture.
Its `request_limits` rows assert encoded JSON byte limits on both sides. Native
`mirror_review` uses zero to mean no native decoding cap; Python retains its 2 MiB
cap. The crypt-write limits also differ intentionally: Python permits 45 MiB while
native decoding permits base64 of 32 MiB plus 64 KiB overhead. Image requests permit
24 MiB and general requests 2 MiB. The fixture makes these differences explicit.

Go `protocol.go` owns decoding/admission and response envelopes; `requests.go`
routes requests into domain owners. Cancellation and credential publication retain
the process-wide operation scopes in `operation_scope.go`.

## Checks for a change

Run tests through the project runner from the repository root:

```sh
python3 dev.py test desktop 'test_rclone_*.py' --mode fast
python3 dev.py test desktop test_transfer_adapters.py --mode fast
python3 dev.py test mobile 'test_mirror_*.py' --mode fast
python3 dev.py test mobile 'test_*transfer*.py' --mode fast
python3 dev.py test mobile test_bridge_protocol.py --mode fast
python3 dev.py test bridge --profile smoke --mode fast
```

The native service tests cover captured mapping changes, generation revocation,
storage relocation, cancellation retirement and incomplete approval. Mirror tests
cover changed records, path/link rejection, crypt preflight and partial transfers.
Desktop outcome tests distinguish launch acceptance from completed success.
Use [history](history/history.md) only for earlier implementation context.
