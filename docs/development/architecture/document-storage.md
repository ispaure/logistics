# Document storage sessions

`services/documents/storage.py:DocumentResource` retains provider access, reads
bounded bytes and captures a revision. Providers own encryption, credentials and
publication. Formats own validation, serialization and size limits. The host
owns routing and `DocumentPolicy`, including read-only wrapper restrictions.
Failed or cancelled saves retain the draft and previous baseline.

## Streaming local exports

`stage_local_document_export` defaults to exclusive creation. For an approved
replacement, capture `local_document_export_revision` at confirmation and pass
it as `expected_revision`, including through SSH retrieval. Stage, verify and
check cancellation before publication. Revision checking and rename are separate
filesystem operations. Declining consent prevents transfer.

## Trace a mobile provider reader

Start at `mobile.private_sessions.PrivateSessions.open()` for admission and route
identity. `ProviderDocumentOpening` prepares, builds unpublished controls through
`provider_view.py`, then adopts the reader into `ProviderDocumentSession`.
Format controls belong to the feature.

| Source | Reader path |
| --- | --- |
| Remote or rclone crypt | `features/rclone/mobile/remote_resources.py` → `remote_readers.py` → `RemoteSource`, with generation-bound ranges or RAM archive snapshot |
| Offline LocalCrypt | `CryptContentProvider.content_source()` → `NativeSource` or bounded `DecodedContent` |
| Generic provider | `services/documents/provider_documents.py` → commonUtils `ProviderContent` → provider content factory |

The native rclone bridge exposes decoded ranges and bounded RAM archives for
remote and LocalCrypt reads. `NativeArchiveAccess` publishes cached members only
if the source and inner-password revision are still current. Terminal close
clears caches and rejects late completions. Browser close releases its own grant.
Adopted readers retain independent access until disposal or credential
replacement. Failed opens retire newly acquired resources. A supplied prepared
reader remains caller-owned until adoption. Check `test_localcrypt_access.py` and
`test_remote_service.py` in the mobile host suite.

## Privacy and lifetime

Private and remote sessions stay out of ordinary recovery and history. The host
handles lock, revocation and plaintext export consent. The provider still
validates the grant and revision during I/O. Desktop `DocumentProtection` composes
wrapper restrictions, concealment, revocation and resume proof. Failed cleanup
stays locked and retains release handles for retry. Private notebook WebViews use
nonpersistent storage. See [access and privacy](access-privacy.md).

`EditorPicker` captures the source policy for text and notebook Save As. For
private-to-ordinary export, obtain `confirm_plaintext()` and recheck the operation,
origin and destination after dialogs. `DestinationRequest` distinguishes
unchanged storage from a saved file that failed to reopen. Keep the source draft
until a successful handoff. Check `test_editor_picker.py`.

`DocumentReadCapabilities` declares privacy, write access, credential lifetime,
offline availability and remote access independently. `required_feature` is a
separate admission check. Ordinary Local remains available with rclone disabled.
Unknown compatibility adapters default to private and credential-bound.
`document_source` dispatches optional provider hooks or the generic reader.

## Independent text documents

The QApplication-owned EditorService retains one window per document, even
after the originating browser closes. Open reuses the existing buffer.
`DocumentsPage` owns dock tabs. `request_document_close()` returns
`CloseOutcome.ACCEPTED`, `VETOED` or `PENDING` so the host can distinguish Cancel
from asynchronous retirement. The owner handles prompts and publishes `idle`.
Plain windows retain native close vetoes, and legacy `prepare_close()` can defer
closure.

## Shared document workspace

`workspace.py` keeps a 64 KiB/32-item ordinary manifest of managed UUIDs and whitelisted state, including per-text Edit/Preview. It preserves malformed input. Transient providers stay in memory. Callbacks capture session owner and generation. Replacement hosts retire old callbacks and pending private work. [Workspace navigation](mobile-workspace-navigation.md) owns adaptive panes and [window isolation](mobile-workspace-navigation.md#independent-uikit-scenes).

| Contract | Owner |
| --- | --- |
| Private edit/save | `documents.py` bounds text to 1 MiB, preserves encoding/endings and checkpoints atomic UUID-based drafts. Stale/deleted originals require conflict handling. |
| Import copy | `access.py` and `pickers.py` stream scoped URI/URL grants, then release them. |
| Preview | `preview.py` renders bounded offline Markdown with escaped raw input. |

### Explicit text-session close

Close prompts on the captured dirty owner with Save, Keep draft, Discard or Cancel. Save/checkpoint failures retain the session. Discard reads and checkpoints current bounded source bytes without writing the original. Private sessions omit durable Keep. See [draft checkpointing](mobile-runtime.md#startup-and-document-responsiveness). Unavailable restored entries can retry or remove the workspace entry while preserving saved data.

### Memory-only provider sessions

`PrivateSessions` admits four controllers and 32 MiB of whole-file input. Identity is opaque and ordinary manifests omit all provider entries. Clean decoder resources release on inactivity or memory pressure; dirty text and forms remain until saved or discarded. Credential reload/forget checks every dirty owner before invalidating generations. `native_private_workspace` covers two encrypted drafts, cancellation and callback retirement.

## Publication and compatibility

- `publish_document_stream` and `document_transaction` own archive metadata
  publication and local backup callbacks. Desktop text retains its encoding,
  permission and conflict adapter. Private formatted Markdown falls back to
  Source on unsupported native backends.
- Android Local and Received Files share `MobileLocalFiles`. When SD-card/FUSE
  rejects exclusive rename, copy into an exclusively created target, verify and
  remove staging. The target may be visible during copying. A changed
  post-publication revision permits one stable read matching SHA-256 and format.
- The public-layout migration journals moves. Local and copy references use
  `Files://`, `RcloneCopies://` and `RcloneCopiesEncrypted://`. Resolve against
  current roots and migrate legacy progress on use. `ResourceImports` merges
  under a process-local lock and preserves invalid or linked indexes.
- Verified renames reconcile Recent, favourites, and saved library roots by
  logical path. LocalCrypt catalogs stay encrypted. If a separate open desktop
  buffer loses its source, preserve its draft through Save As. See [reader
  state](reader-state.md) and [LocalCrypt](../../features/rclone/development/localcrypt.md).

Recovery verification belongs with the adapter. In the Android rename fallback,
failed copying removes its partial target. Verification or staging cleanup
failure reports the incomplete mutation. The legacy-layout migration records
paths before moving files, keeps unclassified folders in Rclone Copies and
moves loose files and explicit Notes Libraries to ordinary Files. Startup waits
for the migration worker. Managed aliases resolve legacy positions and
bookmarks when the document next opens or unlocks. Received Files keeps its
import identity across SD-card relocation and rejects links. Use
`test_resource_imports.py` for stale index instances and malformed index retention.

For provider renames, update both file and descendant references only after the
mutation commits. Reconcile desktop favourites and Recent independently so a
catalogue failure cannot block the other. Mobile reconciles on the UI loop even
after picker cancellation if the provider already committed. Encrypted imports
keep their stable record keys and update display names. Run the rename-reference
and LocalCrypt rename tests for persisted identities.

## Imported metadata publication

`Python/mobile/library_edits.py` replaces the managed UUID copy after revision and checksum validation. A bounded journal recovers matching before/after digests on open and stays available on conflict. Check cancellation before each file enters publication. Provider adapters own their transactions and credentials.

## Document action matrix

| Format | Local and writable LocalCrypt | Cloud |
| --- | --- | --- |
| Text and Markdown | Create, edit, Save, Save As | Read-only preview |
| Notebook `.rmdoc` | Create, edit, Save, Save As, Export Copy | Direct open unavailable |
| PDF and images | Read or preview | Bounded preview |
| EPUB and supported comics | Read and edit supported metadata | Read-only preview |

Image Tools runs separate filesystem batches. Text and Markdown limits are
16 MiB and 8 MiB on desktop LocalCrypt, respectively, and 1 MiB for mobile
editing. The notebook parser admits up to 128 MiB compressed, 256 MiB expanded
and 65,536 entries. Mobile LocalCrypt's `crypt_write_buffer` stages up to
32 MiB directly as ciphertext. See [notebook storage and recovery](../../features/notebooks/development/development.md#editing-and-recovery).

Ordinary notebook recovery distinguishes successful publication, uncertain
durability and unknown outcome. Keep the draft for recovery or Save As when
its original folder is unavailable. A verified Move/Rename can retarget the
open session without losing undo state. Ordinary Export Copy verifies the
destination and rejects host-protected provider roots.

For a mobile Move or Rename, start at `mobile/document_mutations.py`.
`prepare_document_mutation` flushes queued edits and captures open sessions on
the UI thread. `DocumentMutation.execute` verifies the saved baselines and
moves storage on a worker. It returns a handoff with reopened text documents
and notebooks, plus any progress or reference errors. `apply` checks each
session's current identity before retargeting its editor on the UI thread.

For mobile Create, `document_choices.py` opens `EditorPicker` with name, format
and provider location in one route. Construct notebook bytes from the final
validated name. Cancel returns to the origin. Retire the route before opening
a successful result. Retry an initial folder listing only while its route and
credential identities remain current.

## Notebook host actions and deletion

`services/documents/mobile_notebooks.py` composes Create, Show in Folder and
Delete. Keep the final name and provider choice in the shared picker. `Export
Copy` leaves the source binding intact. `DocumentResource.delete()` checks write
capability, grant, cancellation and expected revision. Capture and recheck the
active session, source and single-window state around confirmation.

Source deletion and ordinary recovery cleanup are separate steps. A partial
success keeps the draft open, disables Save/checkpoints and permits Save As or
retry of unfinished cleanup without deleting a replacement file. Hold the busy
reservation until a cancelled worker settles. Reconcile Recent and close after
cleanup. Private notebooks have no ordinary recovery directory.
`test_discard_reopen.py` checks retained bytes and discarded drafts.

## Enforced architecture contract

Run `python3 dev.py architecture`. Every editor package listed in
`Scripts/architecture.json` inherits the guard recursively. The checker classifies
new launchers and rejects concrete backends, aliases/deferred factories, raw file
I/O and direct provider mutations. Persistence exceptions name the module,
function, operation and reason. Archive callbacks retain their shared transaction
entry. `test_document_architecture.py` injects forbidden mutations and registrations.
Native and runtime privacy behavior have separate checks.

See [commonUtils provider contracts](../../../Python/commonUtils/docs/development/reference/ui/resource-providers.md)
for content factories and replacement. Run `python3 dev.py test-owner document-services`
for host storage regressions. Notes Library uses the same provider boundary for
contained, verified authoring and tree mutations while keeping its own navigation.
