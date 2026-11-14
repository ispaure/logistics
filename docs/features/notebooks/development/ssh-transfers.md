# reMarkable upload preparation and mutation qualification

Start at **Debug → Notebooks → Retrieve RMDOC from reMarkable Tablet…** on
desktop. `remarkable_ssh.list_snapshot` builds the read-only tree from native
UUID metadata. `export_document` streams an opaque-member-preserving RMDOC.
Use the desktop host fixtures to change the browser without a tablet:

```sh
python3 dev.py test desktop --exact-file Python/tests/notebooks/test_remarkable_retrieval.py
```

Expect synthetic folders and documents to retain their identities across refresh
and reconnect. In `ui/remarkable_destination.py`, configure native Save mode and
the default suffix before overwrite confirmation. Publish only to the accepted
local path and check the captured revision before replacing it. See
[streaming local exports](../../../development/document-storage.md#streaming-local-exports).

`remarkable_transfer.prepare_upload` prepares a local candidate, and
`compare_upload_members` checks a scoped copy against its receipt. Upload and
tablet organize controls remain unavailable while device qualification is open.

## Local candidate contract

`prepare_upload(data: bytes, cancelled=...)` returns `PreparedUpload(archive,
receipt)`. The immutable `UploadReceipt` records the source and candidate SHA-256,
native document ID, ordered active page IDs, resulting file type, whether
backgrounds were converted, and each member's name, size and SHA-256. This is a
local content receipt, not an acknowledgement from a tablet. Member names are
source data; keep receipts private when working with a personal archive.

Preparation uses the existing bounded `Notebook.read` parser: 128 MiB compressed,
256 MiB expanded and 65,536 ZIP entries, with path, entry-type, compression and CRC
checks. It requires native document/page UUIDs and live document metadata. It
accepts document-owned members and top-level native template assets, preserves
opaque members, and checks active page scenes, referenced PNG resources and PDF
page mappings. PNG support follows the existing noninterlaced eight-bit,
four-megapixel capture validator. Deleted modern page records and their opaque
members remain preserved; their inactive scenes are not interpreted. An absent
page-scene member follows the existing parser's blank-page convention; referenced
image resources must exist.
Modern `cPages` candidates must explicitly declare integer `formatVersion: 2`.
Preparation rejects mixed legacy-version/modern-table metadata without repairing
it or changing the permissive, byte-preserving read/retrieval path. This version
check does not qualify the remaining modern metadata fields for every firmware.

For supported stock/blank notebooks and existing PDF-backed documents, the
candidate is the exact input byte sequence. For supported custom Logistics
backgrounds, preparation calls the existing portable PDF-background exporter,
then reopens and validates the result. Original ink, image resources and opaque
members must remain byte-identical; only the known metadata, content and pagedata
sidecars may change, and the PDF/background export may add members. The source
bytes are unchanged. Existing IDs and parent links are retained for the receiving
importer to interpret; this is not a fresh-ID copy or a direct-store replacement.

EPUB-backed editing, encrypted PDF backgrounds, unavailable active templates,
unsupported active scene objects, missing resources and unrelated members are
outside preparation support. Opaque SSH retrieval continues to preserve these
formats without imposing the preparation/editor limits. Rejection is a local
qualification result, not a claim that the tablet cannot open the document.
Cancellation raises without returning a candidate. ZIP parsing itself is bounded
but not interruptible between every compressed chunk.

## Recovery comparison

`compare_upload_members(receipt, observed, cancelled=...)` takes a mapping of
relative member names to bytes from a separately scoped staging copy. It reports
sorted `missing`, `changed` and `unexpected` names. `complete` means all member
bytes match the receipt; it does not mean the remote document is visible, indexed,
synced or safe to replace. It never repairs, retries or removes anything.

Before a future mutation backend can use this check, it must establish ownership
of staging files, persist a transaction record and original metadata outside the
live namespace, and verify the destination revision under the device's actual
writer exclusion mechanism. On interruption, compare the scoped staged data and
the current destination before deciding whether to finish or restore. Changed
destination data or unexpected staging members require reconciliation; neither
may be overwritten or deleted merely because a retry was requested. A local
hash match alone cannot provide a multi-file device transaction.

## Organize and publication contract still to qualify

| Operation | Required behavior before it can be enabled |
| --- | --- |
| Upload a new document | Receiving importer or verified firmware adapter owns fresh IDs, parent assignment, collision handling, complete asset publication and index refresh. Never infer absence from the visible browser snapshot: unknown, unreadable, deleted or orphaned records may occupy an ID. |
| Rename | Target an exact native UUID; preserve unrelated metadata fields; verify the revision and the native library's resulting name after refresh. Same display names need not imply the same document. |
| Create folder | Use the firmware's collection schema and identity allocation; verify empty-folder visibility and parent indexing. Root and display-only Unfiled are not native collections. |
| Move | Verify a real live destination collection and complete native ancestry; reject self/descendant moves and malformed ancestry. The browser's repaired display tree is not mutation authority. |
| Copy | Allocate a new document identity through a qualified importer/adapter; preserve page/asset references and source bytes. Replacing filename prefixes alone is insufficient for unknown native records. |
| Delete/restore | Establish the firmware's trash/tombstone and sync behavior on disposable content. Do not equate native deletion with recursively unlinking files. |
| Interruption/recovery | Verify writer exclusion, publication ordering, revision conflicts and restart/index behavior across a disconnect. Retain an owned recovery record until native acceptance succeeds. |

reMarkable documents the shared UUID filename layout, instructs that Xochitl
should be stopped during document-store access or modification, and provides no
cross-version compatibility guarantee. Xochitl also participates in encrypted
device startup. These are constraints for a future adapter; the browser never
stops services and its current read-only listing/export is not an atomic firmware
snapshot. [Official Xochitl storage guidance](https://developer.remarkable.com/documentation/xochitl)

The supported USB web interface accepts `.rmdoc` imports. That importer is an
alternative for a separately authorized native acceptance exercise; support for
that route does not prove direct SSH publication is safe.
[Official importing and exporting guidance](https://support.remarkable.com/articles/Knowledge/importing-and-exporting-files)

## Evidence and exact device work needed

Tracked synthetic fixtures cover legacy page arrays, modern `cPages` records,
deleted records, native ink, PNG resources and PDF-backed notebooks. Preparation
regressions verify exact preservation, portable background conversion, rejected
unsupported/incomplete inputs, cancellation and incomplete/conflicting/foreign
staging members. Existing verified synthetic companion-app import evidence
supports the PDF-background route; it does not establish SSH mutation, physical
stylus behavior or recovery on a named firmware.

The following work requires separate device authorization and must stay within
disposable synthetic documents:

1. Read the model and exact software version from the tablet's About screen,
   omitting serial numbers. Record the current Xochitl/rm-sync service states.
   This identifies a qualification target; it does not grant mutation support.
2. In the tablet's native UI, create an empty disposable folder and a synthetic
   notebook. Capture only those known UUIDs' metadata/content before and after
   rename, move into a second disposable folder, trash and restore. This resolves
   collection schema, parent changes, revision fields and trash semantics without
   reading the personal corpus.
3. Import the prepared synthetic legacy, modern, PNG and PDF candidates through
   the USB interface; reopen them, make a native ink edit, export and compare the
   result. Record assigned IDs and only the disposable items' store sidecars.
   This qualifies the importer and supported package shapes for that firmware.
4. Before implementing direct SSH publication, separately authorize a disposable
   transaction exercise covering service quiescence/restart, staged publication,
   disconnect at each boundary, conflicting edits, cleanup and native visibility
   after recovery. Preserve existing device data and remove only explicitly
   owned synthetic items using the qualified native mechanism.

Until those results exist, no firmware profile grants upload or organize
capabilities. Do not promote a synthetic filesystem test into device acceptance.

## Scoped reads and local metadata plans

`remarkable_ssh.read_sidecars` reads raw metadata and optional content for an
explicit bounded set of native IDs without listing the library. It rejects
missing metadata, duplicate or foreign members, links and oversized records.
These records are revision inputs; reading them while Xochitl is active does not
make them an atomic snapshot.

`ssh_connection` owns one authenticated POSIX OpenSSH master for a bounded batch.
It uses the existing host verification and askpass path, retires its private
control socket on exit, and prevents clients from falling back to another login
when the master disappears. `ssh_stream` can reuse that connection and stream
immutable input concurrently with output. Cancellation terminates owned client
processes. `export_document` can reuse the same connection for exact-ID
retrieval. The existing standalone read/retrieve route remains available.

`remarkable_mutations.plan_metadata_change` prepares rename, move, trash and
explicit-destination restore from raw metadata. It preserves unknown fields,
advances the native modification timestamp, and guards the target and consumed
ancestor records by SHA-256. Missing, malformed, deleted or cyclic ancestry
blocks the plan. The display snapshot's repaired hierarchy is never write
authority. Exact no-ops retain the original bytes and timestamp.
`verify_metadata_revisions` rejects stale records. Neither helper writes to a
device or qualifies writer exclusion, publication, restart or native acceptance.

`remarkable_transaction.prepare_metadata_transaction` builds an immutable payload
and commands for a single metadata replacement. It performs no I/O and does not
enable browser write controls. Its firmware qualification procedure uses a
private transaction directory outside the native store, an exclusive writer
lease, revision checks after stopping Xochitl/rm-sync, a preserved original, and
an atomic same-filesystem rename. Document content is never part of this write.
All supported writers must respect that exclusion; the lease cannot coordinate
unrelated root processes that edit the store themselves.

A detached transient systemd service owns publication and a bounded
`ExecStopPost` restart. Recovery classifies the target as original, committed or
conflicting without replacing unexpected data. Receipt failures do not precede
the interface restart. A failed restart retains the writer lease and recovery
files. Cleanup requires a terminal job, a restored-service receipt, an owned
manifest and only expected regular files. Failed uploads and conflicting stages
remain for reconciliation; callers must retain the transaction token before
upload and must not retry blindly. Synthetic shell/service tests cover these
boundaries, including process termination before and after rename. Actual
firmware detachment, restart and native acceptance still require qualification.
[systemd service lifecycle](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)

The receipt inspector uses shell `read` for its fixed outcome values. The
observed firmware's reduced BusyBox `head` does not support `-c`; requiring that
option interrupted an initial readback despite completed service restoration.

On November 13, 2026, a disposable USB import on user-reported firmware 3.29.1.0
returned HTTP 201, but the user saw only its two PDF backgrounds. The native
re-export confirmed that the embedded PDF remained byte-identical while both
native ink files and the PNG resource were absent; the importer also assigned
new document and page IDs. The original synthetic fixture incorrectly combined
`formatVersion: 1` with `cPages`. Preparation now rejects that combination. This
is a confirmed failed preservation check; the inconsistent version is a suspected
cause, not a proven complete diagnosis. A separate format-version-2 candidate
preserved the PDF, PNG and second-page ink, but its rewritten first-page scene
lost a horizontal stroke beside an image. Three subsequent diagnostic pages
retained their scene bytes after viewing without edits; that does not qualify
native ink saving or establish a repair.

Matched pen-edit checks isolated mixed-object sequence anchors. A mutual
next/previous chain lost a stroke. Using only left anchors preserved the normal
ink–image–ink arrangement, but moving an image before or after the strokes still
lost an object whose anchor had a newer native ID. Changing physical frame order
alone did not repair those cases.

The mixed-scene writer now reconstructs insertion anchors in native ID clock
order, so both anchors refer only to older objects. It preserves IDs, physical
frame order, geometry, resources and unrelated frames. The two previously failing
arrangements then preserved every original stroke, image, stacking position,
PNG resource and PDF byte after native pen edits, saving and USB re-export on
user-reported firmware 3.29.1.0. Host regression coverage checks anchor age,
dependencies, arrangement and preservation. This bounded result does not qualify
every scene type or tablet mutation. Folder creation and cleanup of the disposable
test items into Trash were user-confirmed.

The user then restored one disposable notebook and both empty folders. Exact-ID
USB re-exports verified native rename, movement into the first folder and then
the second, trash, and a user-directed restore to My files. Rename changed only
the name and modification time; movement, trash and restore changed only parent
and modification time. All content members remained byte-identical. This does
not establish an automatic restore destination. A subsequent scoped SSH read
confirmed the two collection records have no content sidecar, all three records
are at root, and Xochitl/rm-sync are active. The model is still unidentified.
These checks establish observed native UI semantics on user-reported 3.29.1.0;
direct SSH publication, recovery and the remaining integrated controls remain
unqualified.

An explicitly authorized direct-metadata trial on hardware identifying itself
as `reMarkable Chiappa`, with systemd 259.5 and user-reported firmware 3.29.1.0,
rejected a stale destination guard without changing the document. Rename and
moves through two disposable folders subsequently preserved every original
content member in native USB exports. The rename job survived an SSH client
disconnect after submission. A later trash checkpoint lost its connection;
read-only uptime checks established that a device reboot had occurred. The
current trash metadata and all original content were then recovered over SSH.
Interface and sync services were running without restart-count increases during
the observation window. The reboot cause is not established.

The trial was stopped. No further restart-based tests or firmware write
capability were enabled. Return-to-root/rename-back acceptance remains unfinished;
the disposable copy was left in native Trash to avoid further interface
interruption. This result does not qualify the stop/start publication procedure
for that firmware, even though the inspected document bytes survived. Keep the
browser read-only while the restart behavior and recovery boundary are unresolved.

Subsequent cleanup preserved local recovery evidence, verified that every owned
test unit was inactive, and removed only the five transaction directories, their
stale lease and the empty transaction root. The notebook metadata remained
unchanged and interface/sync service start times and restart counts stayed
unchanged. Cleanup did not start, stop or restart those services. The disposable
copy remains in Trash; this housekeeping does not complete writer qualification.
