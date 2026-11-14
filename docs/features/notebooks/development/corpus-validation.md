# Read-only corpus validation preparation

The reusable owners are `Python/tests/notebooks/corpus_receipts.py`,
`corpus_prepare.py`, `corpus_calibration.py` and their focused regression tests.
The command-line rehearsal generates synthetic fixtures only. It accepts no
host, port, credential, source-file or live-acquisition option. Its transport
replaces `ssh_stream` with generated TAR streams while exercising production
`list_snapshot` and `export_document`. It never calls tablet writers or service
controls. A successful rehearsal is not permission to read a personal corpus.

## Run the synthetic rehearsal

Use an isolated source snapshot, its own desktop environment and the Build
Manager revision pinned by that source. From the snapshot root, choose a new
ignored output directory:

```sh
BUILD_MANAGER_DEPENDENCIES=project PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$PWD/Python:$PWD" .venv/bin/python \
  -m logistics_build.build_retention --scratch \
  "$PWD/.venv/bin/python" -m tests.notebooks.corpus_prepare --conservative \
  --output "$PWD/test-results/corpus-conservative"
```

Omit `--conservative` for the strict fixture-only pixel and edit/save/reopen
rehearsal. The conservative fixtures include plain and legacy/modern PDF books,
blank and hidden ink, preservation-only bytes, EPUB backing and mixed ink/image
stacking. Modern PDF fixtures use `formatVersion: 2` with `cPages`; they do not
pair a legacy version with a modern page table.

The scratch wrapper redirects application storage. Each real desktop workspace
uses scratch recovery and a disposable local copy. Originals and owner-only JSON
receipts remain in the ignored output directory; editable copies and recovery
are removed with scratch. No device or simulator is needed.

## Explicit inventory and receipt scope

`run_batch(snapshot, workspace, retrieve, inspect_editor, document_ids=...)`
processes only explicitly selected visible document IDs. The default empty
selection performs no retrieval or editor work. Unknown IDs, folder IDs and
duplicates are rejected before workspace creation. Selection is not connection
authorization: the injected callback is trusted test/caller code, and this module
does not provide a live transport adapter.

Schema 3 binds the exact ID selection and captured inventory on resume. Titles
never determine export filenames. Each real folder and visible document has one
row; unselected documents are `not_selected`. The immutable metadata inventory
also records excluded IDs, reasons, occurrences and read issues, plus unidentified
occurrences. Visible documents, folders and exclusions reconcile to the identified
inventory. Duplicate occurrences and unidentified entries remain separate counts.
Reconciliation does not prove an atomic tablet snapshot or resolve unknown IDs.

The retrieval callback takes `(stable_id, destination)` and must publish only the
requested immutable export into its UUID destination. The editor callback takes
`(source_path, sampled_pages, receipt)` and works only on a disposable copy. Use a
trusted private local workspace with one writer. Checkpoints retain retrieval,
archive/open setup and completed items; handled interrupts also retain completed
editor phases. The sample is first, middle and last page, without duplicates.

Resume requires identical inventory/selection and matching SHA-256 for every
reused export. Changed, missing or interrupted unverified files are preserved and
rejected, never silently reacquired into that manifest. Editor checks rerun on
fresh copies. Hash reuse proves the local archive identity, not remote freshness.
Schema-2 receipts are rejected without migration or rewriting. Keep historical
receipts with their original source/dependency hashes; current tests produce new
receipts in a new directory. The summary records source commits and harness hashes.

## Conservative actual-editor observations

`desktop_inspector(scratch_workspace)` opens the normal desktop resource and
`NotebookWorkspace` path. It compares page IDs with the parsed source, checks the
requested page/count, delivered stroke/image counts and scene order, verifies
usable canvas geometry, and waits for supplied backgrounds and visible images
to decode. Blank, multiple, white, hidden or off-page strokes have no invented
pixel threshold.

Successful delivery is `page_render_observed`; visual correctness remains
unverified. Preservation-only pages and unavailable visible template artwork
are `page_render_unsupported`. A locked PDF is `page_render_blocked` with
`password_required`; the harness supplies no password. The reader's explicit
unsupported backing-type gate becomes `editor_open_unsupported`, while corrupt
metadata and other errors stay failures. A failing or unsupported item does not
prevent later items from receiving a result. Source hashes are checked afterward.

Unknown documents are not edited: save/reopen stays explicitly untested.
`synthetic=True` opts into known fixture counts/pixels and edit/save/close/reopen.
The strict fixture run adds a stroke only to its disposable copy and checks
original stroke payloads and embedded PDF preservation. These checks are not
physical pointer-input or native firmware acceptance.

The mixed ink/image fixture uses the current writer and synthetic image helper.
Run `test_notebook_images.py` and `test_native_image_fixture.py` alongside the
harness to cover native anchor age, stacking, resources and byte-exact public
fixture regeneration. The bounded native ink/image round-trip result and later
halted metadata trial are recorded in [SSH transfer qualification](ssh-transfers.md).
Do not reopen personal exports or treat those historical observations as new
acceptance. This preparation does not enable remote publication or restart tests.

## PDF calibration

`calibrate()` reports model import, editor canvas payload, save and portable
export/reopen measurements for imported and newly drawn Fineliner/Highlighter
strokes. A plain control and legacy/modern PDFs cover sizes, rotation, offset
crops and PDF user units. Width and geometry expectations are independent numeric
references, with ratios to the control and declared paper-height normalization.
These are model/serialization checks, not measured browser stroke edges, optical
widths, native mobile rendering or firmware matching. See [brush calibration](brush-calibration.md)
for the existing aggregate native reference and its limits.

## Proposed separately authorized corpus session

No corpus session is authorized or enabled by this preparation. One concrete
proposal for the coordinator to present for approval is:

- One read-only session, up to 60 minutes, on one user-confirmed tablet endpoint,
  using its existing approved host key and authentication route. The tablet stays
  awake and quiescent; model/firmware and source pins are recorded. Credentials
  are never placed in manifests or worker handoffs.
- Read top-level native metadata once, including exclusion diagnostics. Select
  all active `DocumentType` IDs under the root and its folder descendants;
  exclude deleted/Trash ancestry. Retain unknown/unreadable entries as unresolved
  outcomes. Bind this exact ID selection to a new private manifest before export.
- Export selected IDs serially through `export_document` into a named owner-only
  ignored workspace, without replacing any existing archive. Use `read_sidecars`
  for exact-ID before/after hashes in batches of at most 256; changed sidecars
  require a changed-during-session disposition, not automatic reuse. Matching
  sidecars are useful change detection, not an atomic content-snapshot guarantee.
- Stop acquisition on cancellation, expiry of the agreed session, transport
  failure or detected change. Keep completed exports and pending counts. A later
  session needs its own authorization and freshness binding; local hash reuse
  alone is insufficient.
- Perform editor observations afterward on disposable local copies. Report
  excluded, unsupported, blocked, failed, observed and untested items separately.
  Review distinct formats/anomalies and arrange separate visual, edit/save and
  mobile acceptance before declaring the corpus validated.

Allow only discovery, scoped sidecar reads and streamed exports. No upload,
import, rename, move, trash, deletion, direct SSH publication, service stop/start,
firmware change or credential/configuration modification belongs to this scope.
Current export and sidecar APIs accept an owned `ssh_connection` to reuse approved
authentication; `list_snapshot` currently makes its own read connection. This
helper must not be opened until the session is separately authorized. Its lifetime
ends with that session; it grants no permission to use writer APIs.

The native picker remains a separate acceptance item. Coordinate all physical
work with the owning executor; a prior disposable-device authorization does not
extend to personal notebooks. Public reports contain redacted totals and fixture
IDs only. Personal stable IDs, titles, paths, originals and derived visuals remain
outside Git, CI attachments and worker messages.
