# Document storage sessions

Document editors consume resources rather than decrypted filesystem paths.
`services/documents/storage.py:DocumentResource` retains independent provider
access, bounds input by the format limit, records a revision and publishes through
commonUtils' verified resource mutations. Closing it releases only that document's
lease. `DocumentPolicy` supplies write and persistence policy; a read-only remote
cannot gain write access through a local cache or wrapper.

## Ownership

The host resolves ordinary folders, LocalCrypt copy references and remote sources.
Providers own encryption, credentials, name mapping and publication mechanics.
Credential replacement never revives an old resource. The document session holds
its last successful baseline; failed or cancelled saves do not advance it.
Publication errors distinguish an unchanged destination from a saved file whose
reopening failed. Consumers keep their draft until a successful handoff.

After publication, a revision change across the verification read permits one
fresh read. Android SD-card/FUSE storage can retain the replaced inode's metadata
until the first open refreshes it. The retry must have a stable revision, match
the published bytes by SHA-256 and pass format validation. Ordinary reads still
reject revision changes; failed verification retains the previous save baseline.

Formats own parsing, validation, serialization, size limits and editing state.
They do not create crypt configurations or write virtual paths to disk.
`ResourceTextSession` remains the commonUtils text adapter. Ordinary desktop text
uses the host's local compatibility adapter to retain its established permissions,
encoding and conflict behavior. Provider-backed Markdown preparation and desktop
presentation belong to `services/documents/markdown.py` and `ui/markdown.py`,
including when the selected provider is LocalCrypt. Mobile adapter composition
belongs to `services/documents/mobile_storage.py`; native archive and metadata
transactions remain with their provider owners.

Comic and EPUB metadata models already accept a generic archive source. Their
streamed rewrite, content-manifest verification and revision-safe publication stay
with that source; ordinary local saves retain their existing backup policy.
Neither format needs to identify a crypt implementation.

## Privacy and lifetime

Private or remote resources cannot use ordinary recovery, history or saved
workspace records. The host owns requested-lock dirty/busy decisions, revocation,
screen privacy and confirmation before publishing private bytes to ordinary
storage. Format canvases receive a checkpoint callback. Provider operations still
validate credentials and revisions during I/O; hiding a view does not authorize a
save after revocation. Memory-only drafts do not imply secure memory erasure.

Private notebook canvases use off-the-record Qt WebEngine profiles or native
nonpersistent mobile WebViews. Android loads even large private HTML directly
in memory, bypassing the toolkit’s disk-backed large-content cache.

A binary buffer save uses the native `crypt_write_buffer` operation, bounded to
32 MiB of input. It encrypts RAM bytes into an exclusive empty ciphertext staging
descriptor. Legacy text editing retains its 1 MiB text contract. Existing file
streams continue using the streamed descriptor transfer path. No plaintext
intermediate file is required.

Desktop hosts register provider guards even for ordinary editors, so Save As
into LocalCrypt starts revocation protection immediately. Guards also validate the
retained credential generation, including a revocation that precedes UI handoff.
Revoked Markdown clears its source, formatted view and cached baselines; late save
acknowledgements cannot revive its content. Failed notebook opening releases the
resource and retires the incomplete window.

Mobile notebook canvas remounting preserves the existing model, dirty flag and
undo history without reading a recovery repository. Ordinary recovery still opens
when its original source folder disappears, detaching the source and preserving
unsaved edits for Save As.

## Consumer integration and checks

The [notebook development guide](../features/notebooks/development/development.md)
covers notebook draft/recovery adapters. The
[LocalCrypt guide](../features/rclone/development/localcrypt.md) owns encryption
and credential policy. Reusable resource API documentation remains in
[commonUtils](../../Python/commonUtils/docs/reference/ui/resource-providers.md).

Focused host contracts live in `Python/tests/resources/test_document_storage.py`,
`Python/tests/resources/test_local_crypt.py` and the mobile document-storage tests.
Native bridge tests cover binary round trips, limits, cancellation and rejection
of nonempty output descriptors. Host tests do not establish native widget or
physical-device behavior.

## Document action matrix

These are Logistics document-editor actions. Creation is offered for text,
Markdown and notebooks; readers do not gain a new document constructor merely
because their storage provider is writable.

| Format | Ordinary Local | LocalCrypt | Cloud |
| --- | --- | --- | --- |
| Text and supported source/configuration files | Create/open, edit, Save and Save As | Same actions through the provider | Supported text previews are read-only |
| Markdown | Create/open, formatted or source editing, Save and Save As | Same actions; document/resources stay in session memory | Read-only preview |
| Notebook `.rmdoc` | Create/open, ink/page/layer editing, Save, Save As and Export Copy | Same document actions; private checkpoints stay in RAM and Save publishes ciphertext | Direct notebook opening and writing unavailable |
| PDF | Open/read | Open/read | Bounded read-only preview |
| EPUB | Open/read and edit supported metadata | Open/read and edit supported metadata | Read-only preview |
| Comics `.cbz` and supported comic ZIPs | Open/read and edit supported metadata | Open/read and edit supported metadata | Read-only preview |
| Images | No document creator/content editor; browser previews and Image Tools are separate | Provider/browser preview support; no document creator/content editor | Bounded PNG/JPEG/WebP preview |

Image Tools' batch WebP conversion and JPG EXIF utilities are filesystem tools,
rather than document editors. They have not been migrated into document sessions.
Archive/password/image support retains each reader's existing format limits.
Desktop text editing is bounded to 16 MiB and Markdown to 8 MiB; mobile text/source
and Markdown editing are bounded to 1 MiB. Notebook archives are bounded to 32 MiB
compressed and 128 MiB expanded, with at most 1,000 pages. Unsupported notebook
scenes remain preserved with their existing editing restrictions.

Ordinary notebook checkpoints support recovery. Private notebook drafts have no
ordinary recovery or saved-history record. A successful Save advances the resource
baseline; Save As retargets the retained editor while Export Copy leaves its source
binding intact. Requested locking refuses busy or unsaved private notebooks;
unexpected credential revocation retires their canvas and pending private picker
material. Mobile Move/Rename retargets open notebook sessions through the existing
verified mutation plan, retaining the draft and undo history.


## Editor boundary

All current document editors enter through the shared host storage family:
`DocumentResource` for bounded bytes, the desktop text compatibility adapter for
encoding/recovery, and `publish_document_stream` / `document_transaction` for
archive metadata. Streaming archives retain their provider transaction and local
backup callbacks; they do not inherit the text or notebook byte limit.

Notebook mobile host composition lives in `services/documents/mobile_notebooks.py`;
the former feature module is a compatibility entry.

Notes Library reads, creation and saves use the same verified resource boundary.
Its location resolution, credential lifetime and private WebView policy belong
to the document host. Mobile file browsers, workspace drawers, Notes Library,
move/rename and saved-source reopening use `document_source` or
`open_provider_document`, including notebook dispatch. `LocalTextCopies` remains a
compatibility import for the host-owned `TextDocumentCopies` adapter.

Format code receives capabilities and persistence policy, rather than choosing
LocalCrypt implementations. Host composition and provider adapters intentionally
still resolve local, LocalCrypt and remote sources. Policy walks provider wrappers,
so a writable local cache cannot grant writes or persistence to a remote source.
Private formatted Markdown fails closed on unsupported native backends and leaves
Source mode available. The boundary regression tests check imports, wrapped remote
policy, Notes Library publication and workspace-drawer notebook dispatch.

Desktop notebook Export Copy uses `export_local_document`: a picker-approved
ordinary destination goes through the same bounded, validated, revision-checked
publication and exact-byte reopening as other resources. It cannot write through
an ordinary path into a host-protected provider root. Export keeps the source
binding intact. EPUB/comic reader privacy follows shared persistence policy,
including provider wrappers; a provider-backed ordinary file remains ordinary.


## Enforced architecture contract

`python dev.py architecture` checks every Python descendant of the text editor,
notebook, EPUB, comic and PDF feature packages. `Scripts/architecture.json`
declares those owners; `Scripts/document_architecture.py` implements the syntax
checks. New nested modules inherit the contract automatically. A new document
launcher or `document_editor_id` outside the declared packages fails until its
storage ownership is classified. Archive workspace tools have separate explicit
filesystem ownership; the vendored notebook scene codec is excluded as upstream
in-memory format code.

The check rejects concrete storage backend imports, literal/deferred backend
factories, backend policy flags, ordinary file opening/byte/text helpers, direct
provider publication/deletion and filesystem publication APIs. It follows ordinary
import and assignment aliases, checks reflective access to guarded methods, and
rejects opaque storage star imports. ZIP writes are reviewed too; serialization
into a known `BytesIO` remains format-owned. Reader editing controls use shared
`document_writable` policy, so wrappers cannot hide read-only storage. Ordinary
notebook/PDF imports and text/XML compatibility reads use bounded host helpers.

Intentional persistence exceptions identify an exact module, qualified function,
operation and reason. They cover recovery/preferences, the ordinary collection
index, anonymous Android PDF memory and existing verified archive callbacks/tools.
Exceptions cannot waive backend selection, do not exempt a whole editor, and fail
when unused. Archive callbacks must retain their declared shared transaction or
streamed-publication entry. Adding a new operation requires a reviewed policy change.

CI runs the architecture command and `test_document_architecture.py`, which injects
forbidden imports, backend flags, aliases, raw exports, provider mutations, new
editor registrations and detached transaction callbacks into temporary source trees.
The check imports no feature or GUI toolkit. It is a static architectural guard,
not a Python sandbox: constructed module names, arbitrary reflection, third-party
writers and dataflow beyond the supported alias forms still require source review.
Runtime storage/privacy regressions remain necessary.


## Notebook host actions and deletion

Mobile notebook chrome, Show in Folder and Delete Document decisions are composed
by `services/documents/mobile_notebooks.py`. The canvas delegates these actions
without importing application navigation, resource-history owners or another
editor's dialog. No notebook-to-host or notebook-to-text-editor dependency
exceptions are needed.

`DocumentResource.delete` requires an admitted file revision, writable wrapper
policy and declared deletion capability. It checks cancellation and active access
inside the provider operation; the provider checks the expected revision again
when removing the file. Directories are not document deletion targets. The
notebook document coordinates this with its ordinary recovery repository, which
owns identity-validated, serialized and idempotent cleanup. Private notebooks have
no ordinary recovery directory.

Confirmation snapshots the document/session and checks the active host and
single-window restriction before and after the decision. Failed source deletion
keeps recovery, history and the editable draft. If source deletion succeeds but
recovery cleanup fails, the draft stays open with an explicit partial-success
error. Retrying finishes recovery cleanup without deleting a new file at the old
path. History/session cleanup follows successful document cleanup, and closing
uses the host's existing discard path. Focused deletion tests cover cancellation,
replacement, credential revocation, wrappers/capabilities and cleanup retries.


## Deletion retry and cancellation review

A live notebook remembers successful source and recovery deletion separately.
Cleanup retries skip both completed phases, preserving replacement files and
recovery records at the old identities. After either phase completes, the draft
becomes read-only: ordinary Save/checkpoints are refused, while Save As and Delete
cleanup retry remain available. The canvas reports the deleted state explicitly.

Delete confirmation also retains the source path/revision and session resource
identity. An in-place move, retarget or baseline change requires another decision.
Only one deletion may own the panel at a time. Cancelling its task keeps the busy
reservation until the filesystem worker settles, because thread cancellation
cannot undo deletion. A still-current canvas receives an interruption response;
a replacement canvas keeps its own busy state. Failed/refused session closing
reports that notebook data was already deleted and restores the prior navigation
intent so closing can be retried safely.
