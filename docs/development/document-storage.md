# Document storage sessions

Document editors consume resources rather than decrypted filesystem paths.
`services/documents/storage.py:DocumentResource` retains independent provider
access, bounds input by the format limit, records a revision and publishes through
commonUtils' verified resource mutations. Closing it releases only that document's
lease. `DocumentPolicy` supplies write and persistence policy; a read-only remote
cannot gain write access through a local cache or wrapper.

## Ownership

`services.documents.destinations.DestinationRequest` captures a picker operation
before worker I/O. It owns destination resolution and publication; its result
distinguishes unchanged storage from successful publication and a saved file that
could not reopen. UI dialogs, current-selection/credential guards and route/editor
handoff remain in `mobile.editor_picker`. Failed reopening retains the source draft.

`DocumentResource.delete()` checks the retained revision before provider deletion.
Notebook documents then ask their ordinary recovery repository to delete that
validated recovery identity. Views do not perform provider deletion or raw recovery
directory cleanup themselves. Private notebook documents have no recovery repository.

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

Mobile Local and Received Files use the same `MobileLocalFiles` publication
adapter. When an Android SD-card/FUSE mount rejects exclusive rename flags, it
creates the destination exclusively, verifies the copied bytes and removes the
staged source. This fallback preserves existing destinations but exposes a partial
file during copying; it does not provide atomic visibility. Failed copying cleans
its partial destination, while verification or source-cleanup failures report an
incomplete mutation for inspection. The notebook creation regression exercises
Received Files with an injected `EINVAL` rename failure. Physical Boox validation
also created and reopened a valid `.rmdoc` on the SD card under Received Files,
rejected duplicate creation without changing its bytes, and removed the temporary
probe app and test directory afterward.

The mobile import index recognizes both Local and its sibling Received Files on
the selected Android drive. Received Files retains its private-storage identity
after relocation; other drive folders remain outside the import boundary. Host
regressions cover notebook creation through editor handoff and reopening from
the SD-card Received Files path, plus identity retention and link rejection.
The updated main app also opened an existing `.rmdoc` from Workspaces → Received
Files on the physical Boox; its data was preserved and only the main Logistics
package remained installed.

Collection and Android device-folder browsing share an ordinary-folder snapshot.
It validates the collection location at listing boundaries rather than reopening
its settings and SD-card marker for every child. Child link, regular-file and
protected-root checks still apply. The device root exposes only Local and
Received Files. Host regressions cover a 120-file snapshot with at most three
collection-location checks, private-folder rejection and cancellation; these
checks do not establish physical Boox latency.

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

Mobile reader adapters declare `DocumentReadCapabilities` in
`services/documents/mobile_reading.py`: privacy, write access, credential-bound
lifetime, offline availability and remote access are separate properties.
An optional `required_feature` declares feature admission separately from privacy
or credential lifetime; a different encrypted provider does not require rclone.
`reading_capabilities` preserves wrapped-provider privacy and read-only rules.
LocalCrypt declares private, writable offline access; Cloud declares private,
read-only credential-bound access without claiming that every remote is encrypted.
Ordinary text adapters derive policy from their provider. Unknown compatibility
adapters default to private, credential-bound sessions.

`commonUtils.runtime.resources.content.ProviderContent` retains independent
content access. Its provider-supplied `content_source` class/function factory can
add decoding and authenticated native archive access. The generic
`services/documents/provider_documents.py:ProviderDocuments` adapter uses that
boundary for text, PDF, EPUB and comics; notebooks retain bounded
`DocumentResource` sessions over the same provider byte contract. See the shared
[content factory and replacement contracts](../../Python/commonUtils/docs/reference/ui/resource-providers.md#injected-content-mechanisms).

Mobile `document_source` selects a provider's optional `document_readers` and
`document_key` hooks, with the generic adapter as its default. It imports no
concrete backend. LocalCrypt's managed and existing offline-copy providers use
one `CryptContentProvider` for native content, ciphertext staging and verified
byte/member replacement. The older copy catalog delegates document I/O to those
providers. Captured access callbacks, rather than the app's current Cloud client,
control reader and Notes Library revocation. A successful editor replacement
retires the old source after adopting its replacement.

Ordinary collection locations and drive migration belong to
`services/documents/locations.py`; ordinary import/reopen routing belongs to
`mobile/document_imports.py`. Local browsing, text opening and picker setup do not
construct Cloud controls. Disabling rclone preserves ordinary document access;
LocalCrypt and remote adapters explicitly retain their rclone feature requirement.

The session manager resolves the selected source, key and password before calling
the generic document opener. `ProviderDocumentSession` owns cancellation and busy
state; existing `_crypt_cancel` and reader-control names remain compatibility
accessors. Newly acquired readers are closed if opening fails before adoption,
regardless of storage type. Supplied prepared readers remain caller-owned until
adoption; an adopted reader is closed by session disposal. Cleanup includes native
PDF handles and archive sources. The opening workflow does not select credentials
or change the global connection's busy state.

`test_storage_independence.py` forbids rclone imports while exercising ordinary
local storage and verifies another private provider's read/save path with rclone
disabled. Shared factory tests cover class injection, revision/cancellation checks
and capability-checked replacement. Real host-bridge regressions cover encrypted
text/archive writes, streamed moves, notebooks and revocation; they do not replace
physical-device UI validation.

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

Recent deletion acceptance uses
`Python/tests/editing/recent_deletion_probe.py --output <evidence-directory>`
with the desktop interpreter and `PYTHONPATH=Python:.`, and
`python -m mobile_build.validation.document_storage_tools android --probe recent-deletion
--device <serial> --output <evidence-directory>` with the mobile interpreter.
Keep evidence under ignored `test-results/`. Both use retention-owned scratch
storage. The Android helper installs an isolated QA identity, collects its result
and screenshot, then uninstalls it; the main app and its data are preserved.
The desktop probe uses Cocoa Qt windows with inspectable Qt message dialogs.

On October 26, 2026, the physical Boox Note Air5 C passed deletion while clean
and edited text/Markdown files were open: live buffers remained accessible,
failed saves retained edits without recreating files, and closed deleted files
disappeared from Recent. A stale Recent row displayed the native missing-file
dialog; an imported EPUB retained its labelled saved copy and reopened after
original-source deletion. Cleanup verified only the main Logistics package
remained. Desktop Cocoa checks cover the same four text/Markdown cases plus
file-watcher warnings and exclusion from Open recent while the buffer is open.
These checks cover ordinary local files and a retained book import, not remote
deletion or encrypted storage.

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

## Mobile creation form

`mobile/document_choices.py` opens the shared `EditorPicker` directly. New
documents choose their name, format and provider folder on one route; there is
no preliminary completion action before location selection. iOS retains a text
**Create document** action, while Android uses the same action in the form.
The selected format validates the filename; notebook bytes are generated from
the final name at publication so renaming cannot leave a stale notebook title.
Cancellation returns to the opening screen and successful creation retires the
route before opening the editor. The shared picker keeps its existing keyboard
compaction, provider validation, collision protection and encryption boundary.
Initial listings retry discarded tokens during cold-start client/credential
restoration, without waiting for cloud setup or accepting stale directory data.


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
