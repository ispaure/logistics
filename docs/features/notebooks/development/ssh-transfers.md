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

The experimental transaction uses an owned private directory, exclusive lease, revision checks under stopped Xochitl/rm-sync, a preserved original and atomic same-filesystem rename. A detached systemd job handles publication and bounded restart. Keep the token before submission. Reconcile unexpected stages or changed destinations before retrying. Require terminal job, service-restoration receipt and expected owned files before cleanup. Retain recovery files and lease on failed restart. See [Xochitl storage guidance](https://developer.remarkable.com/documentation/xochitl).

New transactions record the kernel boot ID before submission. Publication and recovery refuse a changed or unknown boot without service actions. Inspection reports boot continuity and the unit's `LoadState`; an absent transient unit is not proof of completion. Reconcile retained evidence after a reboot instead of replaying recovery. Cleanup rejects any outstanding lease or nonregular member before reading receipts or removing files. These host-tested guards do not qualify the restart procedure on a tablet.

Before enabling native mutations, qualify fresh IDs and asset publication for upload/copy, real collection identities and ancestry for create/move, and trash/restore semantics on owned synthetic content. Separately exercise conflicts, disconnects, restart/index visibility and recovery on the exact hardware and firmware. Use native USB import, pen edit, re-export and member comparison for package acceptance. [Official transfer instructions](https://support.remarkable.com/articles/Knowledge/importing-and-exporting-files)

## Evidence and exact device work needed

- **USB importer, user-reported 3.29.1.0.** A mixed version-1/`cPages` candidate returned HTTP 201 with PDF only. Its two ink files and PNG were absent on re-export. Version-2 diagnostics isolated mixed ink/image insertion anchors. Clock-ordered reconstruction referencing older IDs preserved both previously failing arrangements, including geometry, stacking, PNG and PDF bytes after native pen edits. Qualification is limited to those fixtures.
- **Native UI and scoped reads.** Exact-ID USB re-exports confirmed rename, move, trash and explicit restore to My files with unchanged document content. Scoped SSH reads confirmed collection metadata without content sidecars.
- **Direct-write trial halted.** Hardware identified itself as `reMarkable Chiappa` (exact model unconfirmed), systemd 259.5, user-reported 3.29.1.0. Stale guard rejection, rename, two moves and a post-submit disconnect passed their scoped checks. A later trash checkpoint coincided with a verified reboot of unknown cause. Readback recovered metadata and original content. Return-to-root and rename-back remain unfinished. The disposable copy remains in native Trash.
- **Cleanup and current status.** Owned inactive transaction files and the stale lease were removed after preserving evidence. Service start times and restart counts stayed unchanged during cleanup. Restart/recovery remains unresolved. Keep the browser read-only and direct-write qualification halted. Synthetic corpus rehearsal is complete. Personal-corpus acquisition and end-to-end acceptance are pending.

Host coverage includes `test_remarkable_transfer.py`, `test_remarkable_mutations.py` and `test_remarkable_transaction.py` under `Python/tests/notebooks/`.

## Remaining acceptance

1. **Native macOS save dialog:** one user-operated session with synthetic local files must cover Replace, decline then Cancel, and a new name without the suffix. Verify one replacement confirmation, preserved bytes on decline and the final `.rmdoc` destination. This requires no tablet or SSH login; mocked picker and checked-publication tests already cover the backend.
2. **Read-only corpus:** use the existing stable-ID enumeration/export contract with the corpus owner in a separately authorized session. Preserve the completed USB fixtures and native organization receipts; do not repeat those manual exercises.
3. **Two-way browser:** resolve the unqualified restart/index-refresh contract before another live write trial. Selected-folder upload, fresh-ID copies, folder creation/recursive operations and their collision/recovery UI remain incomplete. Complete their synthetic checks first, then propose a bounded device qualification for the exact hardware/firmware. The new recovery guards do not authorize resuming the halted batch.

No tablet interaction is required to close the completed temporary-file cleanup. Restoring or renaming the disposable notebook in Trash is optional housekeeping, not a prerequisite for read-only retrieval.

The local native-picker attempt on macOS 26.6.2 arm64 / Qt 6.12.0 remains unverified. Its `NSSavePanel` hosted an `NSRemoteView`; trusted accessibility inspection did not expose usable Save/Replace controls, including through a separate inspector and the newly created save-panel service. Watchdog rejection preserved the disposable destination, but does not prove native Replace, decline or Cancel button behavior. Retain the user-operated check above rather than treating this automation limit as a product pass.
