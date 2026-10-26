# Ecosystem refactoring audit — October 25, 2026

This review covers Logistics `bd263369` on `alpha`, its commonUtils checkout
`b105857d` on `main`, and build-deployment-manager `6b727bc8` on `main`. It includes
visible working-tree changes; other conversations were still working when the
owner requested the audit immediately. Findings describe this inspected state,
not a frozen release or a new native acceptance run.

## Implemented follow-up

The scoped recommendations are now implemented. commonUtils `933c398` adds an
explicit reconciliation writer context. Manager `9225924` (building on `bb34d5f`) provides bounded
artifact hashing, cancellable background review, configuration/run-session
owners and common retained-result loading. Logistics adopts that exact local
manager pin; those commits have not been pushed.

`services.documents.destinations` captures filename, bytes, format and provider
before worker I/O, resolves conflicts and returns unchanged, published or
published-but-not-reopened outcomes. The picker retains dialogs, epochs,
credential/navigation guards and editor/route handoff. `Scripts.guest_results`
owns evidence validation, collection state, conditional remote cleanup and final
reports for both guest backends. Platform preparation and transport remain in
their original owners.

The final architecture pass also repairs the earlier notebook extraction's stale
recovery-owner exceptions and distinguishes packaged asset names from module
references. Notebook deletion delegates to `DocumentResource.delete` and the
ordinary recovery repository. Private documents still have no recovery repository.
Native notebook presentation explicitly declares its current host adapters and
reuse of the existing text-editor document decision dialog.

Validation includes all 159 manager contracts on macOS and both dedicated
guests, including cancellation during artifact hashing.
Windows retains three explicit POSIX-only skips. Both guest-result flows pass
and remove their owned test workspaces. The 152-case shared index selection
passes after rerunning the two filesystem-watcher files with native event
delivery; their initial restricted runs remain failed evidence. iOS and Android
disposable probes each pass four creation scenarios and 28 storage scenarios,
with simulator/emulator cleanup verified. Notebook deletion has focused host
coverage; the physical touch/dialog interaction is not newly certified.

The numbered priorities below retain the original evidence and acceptance criteria.

## Repository ownership

The repositories have already undergone substantial consolidation. More value
comes from finishing a few ownership seams than from another package-wide move.

| Repository | Keep here | Keep outside |
| --- | --- | --- |
| Logistics | Feature registration, app navigation, document policy, provider adapters, suites, release gates, source snapshots and pruning policy | Generic execution and reusable library APIs |
| commonUtils | Portable resources/streams/persistence, indexing, reusable Qt/native controls and their contracts | Application destinations, credential workflow, feature discovery and dependency installation policy |
| Build manager | Plans, execution, locking, resources, registration, transport, recovery/review and retention mechanics | Logistics source layout, signing destinations, suite inventory and project storage policy |

The manager has its own commonUtils pin (`f2a0cf1`), independent of Logistics.
Use each project's environment and dependency identity during validation. A shared
API change requires consumer checks before either pin changes.

## Completed work: do not restart these refactors

- Document formats now use `services.documents` resource/session policy rather
  than owning encryption or writing virtual paths as filesystem paths. The
  notebook editor has dedicated drawing, storage and desktop/mobile adapters.
- Mobile controllers have explicit composition/capability access; startup,
  navigation, document lifetime and provider retirement have named owners.
  Remaining large host files do not imply those extractions never happened.
- LM generation, transfer approval/execution, desktop Folder Hub projection and
  feature registration already have separate service/runtime owners.
- commonUtils indexing has a composed scan controller and per-attempt state;
  Markdown editing/search/tables and native browser retirement are consolidated.
- The external manager already owns generic scheduling, subprocess ownership,
  isolated adapters, retained workflow review and recovery. Windows durable
  invocation recovery and explicit Qt parenting are implemented corrections.

The [earlier implementation record](maintenance/remaining-work-audit.md) remains
useful evidence. Its completed C/L/T headings are not today's backlog.

## Priority 1: separate mobile picker requests from publication and presentation

Evidence: [`EditorPicker`](../../Python/mobile/editor_picker.py) is 897 lines in
this review. `save_text_destination` starts at line 763 and combines creation,
text Save As, notebook serialization, privacy confirmation, conflict approval,
worker publication, verification/reopen and route/editor handoff. `PickerWork`
already captures cancellation, epoch, credentials, navigation and location.

The issue is the number of workflow variants sharing mutable picker fields, not
the absence of cancellation guards. A future document type must understand
`creation`, `binary_owner`, source-document privacy and provider-specific reopening
to add one save behavior.

Introduce a captured request describing operation, format, source and destination,
then an application-owned publication result that distinguishes unchanged,
published and published-but-not-reopened outcomes. Keep dialogs, controls and
route projection in the picker. Reuse `DocumentResource.publish`; do not create
another storage API or move application policy into commonUtils.

Acceptance: create/Save As for text and notebooks across Local/LocalCrypt; existing
file conflict and changed destination; credential lock/replacement during work;
cancel during directory creation/publication; source draft retained after failed
reopen; one correct route after success. Start with `test_destination_workflows.py`,
`test_editor_picker.py`, `test_document_creation.py`, `test_notebook_storage.py`
and the existing native destination/storage probes. Host passes do not certify
system pickers or physical SD-card behavior.

## Priority 1: share bounded artifact hashing, then make review asynchronous

The manager's `executor.py` hashes captured artifacts with `read_bytes()`;
`workflows.verify_artifacts` reads both retained and original files completely.
`ManagerPanel.resume_workflow` invokes recovery/checks synchronously. Logistics'
[`distribute_prepared.py`](../../Scripts/distribute_prepared.py) and
[`testflight_tools.py`](../../mobile_build/deployment/testflight_tools.py) also
contain whole-file digest reads.

commonUtils already supplies `runtime.streams.file_sha256` with bounded reads and
cancellation. Adopt that existing primitive for file hashes, preserving the
exact digest. Tree hashes must retain relative-name ordering. In the manager,
run expensive review verification in a retained worker and reject late results
after selection changes. Recheck at effect admission; an asynchronous preview
must not weaken original/captured artifact checks.

This is a source-backed memory/responsiveness risk, not a measured out-of-memory
incident. Validate unchanged digests, missing/changed originals, cancellation,
responsive Qt review and stale-worker retirement. Implement shared adoption in
the manager first, then the project distribution helpers; no new hash library is
needed. Detailed library and manager findings belong in their own developer wikis.

## Priority 2: consolidate guest result lifecycle without merging platform policy

[`Scripts/vm_backend.py`](../../Scripts/vm_backend.py) and
[`Scripts/windows_backend.py`](../../Scripts/windows_backend.py) both coordinate
staging, setup, plan execution, report collection, conditional cleanup and a final
result envelope. Their `run` methods span 164 and 117 lines respectively. Windows
uses durable invocation receipts; Linux includes optional rootless Fedora setup.

Extract an application-owned result/collection scope with explicit staged,
collected, preserved-for-recovery and cleanup outcomes. Keep transport and guest
ownership primitives in the manager and keep platform setup, suite commands and
Logistics report interpretation in Logistics. Do not replace Windows receipt
reconciliation with generic command retries.

Acceptance: transfer failure, accepted command followed by connection loss,
collection failure, cleanup failure, cancellation and a guest initially stopped.
Keep failure evidence before deleting owned guest files. After fixture parity,
use the approved dedicated guests for native checks. Existing October 25 Windows/
Fedora acceptance is historical evidence for those inputs, not for a new extraction.

## Priority 2: explicit index writer context in commonUtils

The shared `filesystem/index/store.py` still combines cache-session access,
scanning, exclusion repair and query APIs. Writer state is correctly initialized
per operation, but helpers reach it through `cache._scan_state`. An explicit
database/generation/state context for one mutation path would make prerequisites
visible. Preserve `DirectoryCache` public methods, snapshots and database schema.

Cancellation/resume, old-reader visibility, rollback, partial indexing and metrics
must remain equivalent. This is a bounded follow-up to completed scan composition,
not a demand to reopen that entire refactor. Removable-volume identity/offline
retention remains a separate policy decision before any schema work.

## Priority 2: reduce manager panel responsibilities

The manager's 900-line `ui.py` still assembles settings/configuration and coordinates
preparation, history, fresh/resumed execution, clocks and approval. Extract a
selection-controls view and a retained run-session owner, using explicit values
and events. `RunView` already exists; preserve it. A mixin with unrestricted panel
attribute access is not an ownership improvement.

Follow with one GUI-free retained-result loader: the executor resume path reads
JSON directly while history applies size/schema/timing checks. Keep engine/plan
identity validation and unknown-provider reconciliation in their existing layers.
Validate malformed/legacy reports through both CLI and GUI before extending schemas.

## Documentation findings and changes

The baseline wikis contain 187 Logistics, 79 commonUtils and 13 manager Markdown
pages. Every folder already has a linked landing and H1 titles. Initial apparent
missing `test.md` links were literal syntax examples, not broken navigation.
The problem was discoverability and some stale workflow descriptions, rather than
empty documentation folders.

This pass adds a practical [Logistics workflow guide](../user/working-safely.md),
commonUtils contribution/refactoring and component troubleshooting guides, and
separate manager user/developer entries with a runnable harmless plan. Existing
topic guides remain canonical; they are not duplicated into consumers.

The mobile capability table and creation workflow now point at current folder-
backed documents and notebooks instead of implying every document is app-private.
The detailed [document guide](../user_mobile/documents/documents.md) owns the
changing creation UI. The [build manager guide](build-manager.md) and
[TestFlight guide](mobile-testflight.md) explain committed source, manual app/Inbox
profiles, dependency wheels and retained distribution outcomes.

## Implementation order and completion criteria

1. Adopt bounded hashing and responsive artifact verification without altering
   checksum or approval contracts.
2. Capture picker requests/publication outcomes while retaining its epoch and
   privacy guards. Validate one operation/format at a time.
3. Extract guest result lifecycle after fixture parity; validate both dedicated
   guest backends before changing normal release plans.
4. Tighten index writer and manager panel/result-loader seams in separate changes.

Each change should reduce implicit dependencies or duplicate failure handling,
preserve saved formats/imports, update its owner guide and pass focused consumer
checks. File length is a pointer for inspection, not an acceptance threshold.
The initial audit changed documentation only; the implementation above is the
subsequent scoped refactoring pass.

## Validation scope

The audit uses tracked/nonignored source inventory, function-body comparison,
import/owner inspection, wiki navigation checks and focused shared/consumer/manager
tests. Exact identical Python function bodies of at least 25 source lines were
not found within the scanned production code; similar workflows still need human
review. Generated outputs, ignored external feature links and raw evidence stay
outside this wiki. Vendored notebook codecs are not refactoring targets.

Fresh checks in this pass all passed:

| Selection | Cases |
| --- | ---: |
| Logistics document/storage/architecture/wiki/viewer selection | 90 |
| Logistics manager adapter contracts | 9 |
| Mobile destination workflows, dummy backend | 14 |
| commonUtils wiki layout, streams, writer state and reconciliation | 37 |
| Manager full portable/offscreen contract suite | 154 |
| Total | 304 |

All 286 wiki pages across the three repositories pass local-link, heading-anchor,
H1 and explicit landing/child-link checks. All 80 Python code blocks parse; the
new bounded-hash and harmless-manager-plan examples execute successfully with
their owning interpreters. The manager plan uses disposable output directories.

Native OS interaction,
VM acceptance, physical devices, external servers, hosted dispatch and new releases
were not exercised for this audit. Other conversations can change the working tree
after inspection; recheck affected source and tests before implementing a finding.

[Developer index](development.md)
