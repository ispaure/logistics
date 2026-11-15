# reMarkable upload preparation and mutation qualification

The desktop **Debug → Notebooks → Retrieve RMDOC from reMarkable Tablet…** browser remains read-only. `remarkable_ssh.list_snapshot` builds the display tree from native UUID metadata. `export_document` streams opaque members unchanged. `ui/remarkable_destination.py` uses native Save mode, sets the suffix before confirmation and checks destination revision. See [streaming local exports](../../../development/architecture/document-storage.md#streaming-local-exports).

```sh
python3 dev.py test desktop --exact-file Python/tests/notebooks/test_remarkable_retrieval.py
```

Expect synthetic folders and documents to keep their UUID identities across refresh and reconnect.

## Local preparation and recovery

- `remarkable_transfer.prepare_upload` validates a bounded RMDOC (128 MiB compressed, 256 MiB expanded, 65,536 entries), native UUIDs and active scenes/resources. Modern `cPages` requires integer `formatVersion: 2`. Preserve deleted records and opaque members. Stock/blank and supported PDF notebooks stay byte-identical. Custom artwork uses portable PDF backgrounds with ink and resources preserved. Reject unavailable templates, unsupported active objects, encrypted PDFs and EPUB-backed documents. Retrieval retains its permissive opaque path.
- `UploadReceipt` records source/candidate and per-member hashes, IDs, order and background conversion. Keep personal receipts private. `compare_upload_members` reports missing, changed and unexpected staged names. A complete match proves byte identity for the scoped copy. Native visibility, indexing and recovery require device checks.
- `remarkable_ssh.read_sidecars` reads explicit bounded UUIDs. `ssh_connection` reuses one authenticated OpenSSH master and retires its private socket. Live reads can span revisions. Treat display-tree repairs as presentation only.
- `remarkable_mutations.plan_metadata_change` guards target and ancestor hashes for rename, move, trash and explicit-destination restore. Preserve unknown fields, reject malformed ancestry and keep no-op bytes. `remarkable_transaction.prepare_metadata_transaction` builds commands for one metadata replacement. Local planning performs no tablet writes.

## Direct publication requirements

The experimental transaction checks target, ancestor and payload hashes before stopping Xochitl/rm-sync. It checks them again after the stop and before the atomic rename. A detached systemd job handles publication and bounded restart. Recovery checks that both services are active before recording restoration and releasing the lease. Keep the token before submission. Reconcile unexpected stages or changed destinations before retrying. Require a terminal job, service-restoration receipt and expected owned files before cleanup. Retain recovery files and the lease on failed restart. See [Xochitl storage guidance](https://developer.remarkable.com/documentation/xochitl).

Before stopping services, the transaction requires both services to have been active for longer than their configured start-limit intervals. It compares the service activation times to a current-boot monotonic journal timestamp. A missing journal timestamp or unreadable service limit rejects the operation before stopping. This is verified locally with synthetic services. [systemd unit start limits](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html#StartLimitIntervalSec=) · [systemd monotonic activation timestamps](https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.systemd1.html#Properties%C2%B6)

New transactions record the kernel boot ID before submission. Publication and recovery refuse a changed or unknown boot. Inspection reports boot continuity, the unit's `LoadState` and whether a start was requested. Once a start has been requested, even a failure or timeout leaves recovery in observation mode. It completes the receipt only after both services are active. Cleanup requires a clear lease and regular owned files. Native write qualification is still pending.

Before enabling native mutations, qualify fresh IDs and asset publication for upload/copy, real collection identities and ancestry for create/move, and trash/restore semantics on owned synthetic content. Separately exercise conflicts, disconnects, restart/index visibility and recovery on the exact hardware and firmware. Use native USB import, pen edit, re-export and member comparison for package acceptance. [Official transfer instructions](https://support.remarkable.com/articles/Knowledge/importing-and-exporting-files)

## Evidence and exact device work needed

- **USB importer, user-reported 3.29.1.0.** A mixed version-1/`cPages` candidate returned HTTP 201 with PDF only. Its two ink files and PNG were absent on re-export. Version-2 diagnostics isolated mixed ink/image insertion anchors. Clock-ordered reconstruction referencing older IDs preserved both previously failing arrangements, including geometry, stacking, PNG and PDF bytes after native pen edits. Qualification is limited to those fixtures.
- **Native UI and scoped reads.** Exact-ID USB re-exports confirmed rename, move, trash and explicit restore to My files with unchanged document content. Scoped SSH reads confirmed collection metadata without content sidecars.
- **Direct-write trial halted.** On the Paper Pro Move (RM03A, firmware 3.29.1.0, systemd 259.5), stale guard rejection, rename, two moves and a post-submit disconnect passed their scoped checks. The following trash operation attempted a fifth Xochitl start inside a ten-minute window. The previous boot journal records `start-limit-hit`, activation of the firmware emergency service, and normal shutdown. The installed emergency script invokes `reboot`. Readback verified that the disposable copy was in Trash and its original content survived.
- **Cleanup and current status.** Owned inactive transaction files and the stale lease were removed after preserving evidence. Service start times and restart counts stayed unchanged during cleanup. The browser remains read-only pending native qualification of the start-window check and recovery. The [read-only corpus validation](corpus-validation.md) ran separately.

Host coverage includes `test_remarkable_transfer.py`, `test_remarkable_mutations.py` and `test_remarkable_transaction.py` under `Python/tests/notebooks/`.

## Remaining acceptance

1. **Read-only corpus:** use the stable-ID enumeration and export contract for authorized reruns. Preserve the existing USB fixtures and native organization receipts.
2. **Two-way browser:** resolve the restart and index refresh behavior before another live write trial. Selected-folder upload, fresh-ID copies, folder creation, recursive operations, and their collision and recovery controls remain incomplete. Complete synthetic checks first, then propose a bounded device test for the exact hardware and software.

The November 15 read-only diagnostic confirmed the reboot chain. Next verify the start-window check on compatible firmware using read-only service and journal queries. Any later writer qualification needs a separate, authorized single operation on a disposable copy, a verified stable interval before stopping, and readback after reindexing.

No tablet interaction is required to close the completed temporary-file cleanup. Restoring or renaming the disposable notebook in Trash is optional housekeeping, not a prerequisite for read-only retrieval.

The user-operated macOS save picker check passed on 2026-11-14 with a synthetic export. It verified Replace, preservation after Cancel, and adding the `.rmdoc` suffix to a new destination.
