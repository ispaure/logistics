# LocalCrypt ownership and data flow

Logistics owns rclone crypt settings, credential sessions, ciphertext mapping and
transfer policy. commonUtils supplies backend-independent browsing, bounded binary
process I/O, range streams and Markdown storage hooks. Its
[provider contracts](../../../../Python/commonUtils/docs/reference/ui/resource-providers.md) are owned
and documented in that repository.

## Initial Pull storage choice

Desktop exposes one Pull action. For a session-loaded crypt remote without a
selected local copy, it opens the LocalCrypt/Local choice with LocalCrypt as the
recommended default. Mobile uses a native question popup for the equivalent
choice, scoped to the selected remote's unsaved credential package. Saved
credentials and non-crypt remotes create Local copies directly through review.
Existing copies retain their storage type. This presentation policy does not
change encryption, transfer routing or existing LocalCrypt mappings.

## Desktop

New LocalCrypt copies require a crypt remote from session-only credentials
(`session.credentials` with the originating ZIP association). A saved config alone
does not satisfy this creation contract. The same session can supply online Cloud
remotes, including those without a local copy. Credential lifetime and persistence
of the ciphertext copy are separate: ending the session preserves the copy.

`features/rclone/localcrypt/mapping.py` maps an absolute credential ZIP path and remote
name to a stable directory under the Logistics per-user application support root's
`LocalCrypt`. `.connections` records contain
only schema, package path and remote name. Schema 2 stores new copies directly at
`LocalCrypt/<remote-name>`. Only schema 2 is loaded/published; the hashed-layout
compatibility branch is removed. Unsupported records and their ciphertext are
preserved without migration or deletion. A same-account unsupported record blocks
publication of a replacement mapping instead of adopting or overwriting data.
Import copy identities and routing helpers from this mapping owner; reader sessions
remain in `localcrypt.backend`. Publication is serialized, rejects case-insensitive name ownership conflicts and untracked
existing destinations, and requires portable folder names rather than silently
sanitizing them. Malformed records are ignored. Package
moves change identity; missing mappings block transfers inside the LocalCrypt
boundary. Roots may be relocated through links, while inner links and hard links
are rejected.

`features/rclone/localcrypt/connections.py` separately associates decrypted copies in
`Server/Local` with their credential package and remote. Its schema-1 records live
in the application support root's `Connections/Local`, outside the sync destination. An accepted Pull
publishes the nonsecret association; rejected transfers do not. GUI acceptance
means the progress job owns the final transfer result, so a partial failed copy
retains its association for retry. Conflicting package ownership blocks Pull
before launching it. Folder sources rediscover these records without a loaded
session, carry the package through `CopyContext`, and prompt to unlock it for
Pull/Push. Existing unassociated folders gain a record on their next session Pull.

`features/rclone/storage.py` derives the application root from
`features.preferences.preferences_path().parent`, including macOS Application
Support/Logistics and the existing Windows/Linux equivalents. On first discovery
it relocates legacy `Server/LocalCrypt` and `Server/.local-connections` directories.
Same-filesystem moves publish without replacement. Cross-filesystem moves and
rebased relative/internal links use private staging, compare file hashes and link
targets with the source, then publish before removing the original. Conflicting
destinations or failed verification preserve source data and report an error.
Readers must be reopened after storage relocation. Decrypted files stay under Local.
Unloaded account sources require both a valid record and an existing copy directory;
loaded account sources can include remote-only names. Orphan records do not produce
folder-list entries.

Pull mirrors the crypt remote's direct backing target into the ciphertext folder.
Push uses the same `push_target` resolver for previews and execution, including
specific-folder selection from an ordinary Push dialog. Ciphertext goes directly
to the backing target and retains its relative encrypted subpath. Missing mappings
and mismatched packages fail before launching a transfer. These are destructive
mirror operations with no rollback; editing does not upload anything.

`CryptResources` builds a private process-local crypt configuration pointing at the
local ciphertext root. Decrypted names and bytes are supplied to generic widgets;
virtual cleartext paths must never be opened directly on disk. Archive reads use
bounded seekable ranges. Markdown saves and comic/EPUB metadata rewrites stream into
rclone stdin, stage only ciphertext, verify when required, check the original
revision and cancellation, then atomically replace the encrypted file.

Initial provider construction and transfer preflight validate the complete
ciphertext tree. Subsequent listings validate the requested physical directory,
its ancestors and immediate children, deferring nested checks until navigation
reaches them. rclone's `lsjson --encrypted` supplies encoded names directly, avoiding
a separate name-encoding process per document. Listing-derived sizes are reused
only when the physical file revision is unchanged across the listing. Archive
streams share revision-keyed range blocks in provider-owned RAM, capped at 32 MiB
and 512 blocks; size metadata is capped at 10,000 files. Cache hits still check
session validity, cancellation and physical revisions. Publication changes the
revision, and provider closure clears the cache. No plaintext disk cache is added.

`localcrypt/read_cache.py:PrivateReadCache` owns the session-private caches and
their retirement lock. Encoded path/directory mappings are also limited to 10,000
recent paths; an evicted mapping is reconstructed through rclone when needed.
`localcrypt/transport.py:CryptCommand` applies the same session launch, revocation,
worker cancellation and output-bound checks to path encoding and document I/O.
`CryptResources` keeps physical path/revision checks and verified replacement
policy. Temporary-save cleanup removes both metadata and plaintext verification
blocks for the staged path, including after provider retirement.

Desktop archive streams use two cached 4 MiB ranges per reader to reduce CLI
startup overhead for large covers. Bounded text/INI reads share the same cache.
Private browser metadata callbacks run under provider cancellation scopes and
return generic `BrowserDetails`; comic and EPUB fields/covers never probe their
virtual cleartext paths on disk. The shared Preview host owns selection changes,
stale result rejection and shutdown. Picker browsers explicitly omit Preview.

The private comic metadata action snapshots the selected ZIP/CBZ files and folders
when the clicked row belongs to the selection; otherwise it edits only that row.
`ComicSelection` scans provider entries/listings for folders, deduplicates virtual
paths without filesystem resolution and caps discovery at 10,000 entries. ZIP
headers must contain supported comic image pages; unrelated ZIPs are ignored.
Provider-backed metadata editors determine folder selection through `entry`,
never `Path.is_dir()` on virtual cleartext names. Minimal archive sources retain
explicit-file selection support. Batch password failures retain the established
skip/report policy, and saves validate all loaded snapshots before per-file
encrypted publication. Page data and untouched metadata remain unchanged.
`CryptBrowserView` connects comic editor `saved` notifications to the selected
item's existing `ResourcePreview.request` worker, so a successful bulk save
invalidates displayed metadata even when the browser selection does not change.
The preview owner coalesces notifications and rejects older in-flight results.
Pull completion does not notify retained browser views; their Refresh command
reloads listings and selected metadata. Provider revision checks invalidate cached
archive bytes after a pull, and a newly opened metadata editor reads that revision.

`ValidatedPasswordDialog` validates credential and file passwords on a worker
before accepting. Failed attempts retain the dialog, show a sanitized inline
error, clear and focus the field. Enter/Return events are consumed in that field
so they cannot also trigger default-button handling. Cancellation waits for
worker retirement. Standalone and workspace private browser factories unlock
before constructing the view; a cancelled factory can return `None` without a
dock being created. No successful session replaces credentials until validation
has completed.

Private sessions are children of the unlocked package session. Forgetting or
replacing the parent recursively revokes its children. Old providers stay revoked
after another unlock; reopen the document to create a fresh provider. Browsers and
independent document windows hold idempotent provider leases; the last release
removes its private credentials. Browser closure waits for its workers and releases
only its own lease, preserving still-open documents. Worker-local cancellation is
propagated to subprocesses and streaming writers. Cancelled opens never present a
window. Completed publication cannot be rolled back by a later cancellation.

Desktop credential imports require every non-directory TXT entry to be encrypted,
including when saving a config. Validation completes before extraction or session
replacement, so plain/mixed packages leave existing credentials intact.
`session.revocation_check` captures a credential generation without copying its
secrets. Sync and comparison subprocesses poll that generation; integrated Qt
transfers receive revocation through a queued signal on their owning thread.
LocalCrypt commands and path encoding include revocation in cancellation and
recheck it before returning output. A new unlock cannot revive an old generation.
Cancellation does not undo transfer changes already published to the destination.

Already displayed document content can remain in RAM after credential revocation;
this is not secure memory erasure. Per-process rclone environments contain keys,
but settings are not written to plaintext config files or command arguments.

## Mobile


Mobile rclone ownership is under `Python/features/rclone/mobile`: bridge/credentials,
transfer jobs, ciphertext copies/providers and their native operation screens.
The app retains generic provider-document controllers in `mobile/provider_ui.py`
and `provider_opening.py`. Storage-neutral reader/editor adapters live in
`services/documents/provider_documents.py`; ordinary locations live in
`services/documents/locations.py`, and native archive facades in
`services/documents/archive_access.py`. Private sessions, format-feature
views, navigation, persistence and screen privacy remain with their existing owners.
The rclone catalog UI subclasses the generic provider UI; generic private-session
controllers inherit `ProviderUI` directly, without inheriting remote download UI.
See the [module ownership map](development.md#mobile-ownership).

Managed `CryptFiles` and existing `DownloadedCryptFile` copies share the
`localcrypt/mobile/content.py:CryptContentProvider` content/write boundary.
`LocalCryptCopies` retains catalog identity and delegates opening and saving to
the provider adapter; it no longer has a separate document transaction engine.
commonUtils' generic content factory knows no rclone commands, credentials or
format editors. The LocalCrypt implementation owns those commands, verified
ciphertext staging and revision-safe publication, including native ZIP metadata
rewrites that preserve untouched members. Byte saves and archive metadata saves
retain their distinct streaming/buffer limits within that one provider contract.


The embedded bridge implements crypt using rclone's cipher over an allowlisted
backing remote in the same credential package. It does not instantiate arbitrary
filesystem or nested wrapper configurations. Validation runs on import and vault
restore before replacing active credentials.

`crypt_fetch` downloads original ciphertext through a caller-owned descriptor.
`features/rclone/localcrypt/mobile/copies.py` stores completed UUID copies under app-private
`LocalCrypt`, with an encrypted relative path, remote and crypt-settings fingerprint.
No decoded filename or key is added to those records. The rclone settings determine
whether original filename encryption is enabled. Incomplete/invalid copies are
excluded. The fingerprint binds an offline copy to its crypt settings independently
of rotating backing OAuth tokens.

The production mobile reader uses `crypt_stat`, `crypt_range` and `crypt_archive`
over caller-owned ciphertext descriptors. A seekable shared RangeReader checks the
file revision and credential generation even on cached reads. Native archive
facades fetch authenticated members lazily; no whole decrypted ZIP view or
plaintext output file is created. `crypt_decode` remains a bounded legacy adapter. The native
reader/editor UI uses session-only text/image widgets and never imports this content
into persistent DocumentStore/LibraryStore records, previews, bookmarks or recents.
EPUBBook accepts an optional generic archive source so portable reading can use
memory without a temporary file. Ordinary EPUB filesystem behavior is unchanged.

Mobile streams encrypted downloads and transfers without a fixed whole-file cap,
text/Markdown editing up to 1 MiB, EPUB chapter text and PNG/JPEG/WebP CBZ pages.
`crypt_encode` writes only to an empty independent ciphertext staging descriptor.
Python verifies staged plaintext through its native archive/range source, checks the original's
revision and cancellation, then atomically replaces the local ciphertext. Shared
`TextSnapshot` preserves encoding, BOM and line endings. Invalid text is rejected
before publication; failed saves retain the editor buffer. Closing, credential
changes and app exit require saving or explicitly discarding dirty edits.

The native ZIP library authenticates AES/ZipCrypto members individually. Passwords
are supplied per open and never saved; opening verifies a protected member before
presenting the reader. Header/member/image buffers remain bounded independently
of the outer archive size. `crypt_manifest` hashes authenticated member streams
for before/after verification, including members larger than the read buffer. Metadata saves use `crypt_metadata`: authenticate the original inner
archive, replace only its metadata member, copy all other compressed/encrypted
entries verbatim, then encrypt the result into an exclusive staging descriptor.
The host verifies a shared content manifest and reparses the document before
atomic publication. Rewritten protected metadata uses AES-256 with the same inner
password; untouched entries retain their original protection. Mobile has no upload
or folder mirror.
Desktop ciphertext-copy directories are not imported as a mobile library. Close
clears reader references; credential import/reload/forget also clears displayed
private content and decrypted copy labels. OS memory/backup policies are outside application-level persistence rules.

## Shared metadata editing

`services/documents/metadata.py` owns comic/EPUB metadata plans, resource manifests
and the streamed rewrite shared by ordinary and private desktop saves. Existing
ComicInfo and EPUB package serializers preserve unknown XML and page/resource
metadata. Storage adapters own publication: desktop uses `CryptResources`;
mobile uses the native bounded raw-entry rewrite and the same Python manifests.
The mobile text and metadata paths share one staging, conflict and cancellation
transaction. Neither path creates a plaintext staging file or backup.

EPUBBook's generic source accepts an optional inner password and rejects changes
during loading. Desktop's existing metadata form/window accepts the private source,
keeps its provider lease and prompts for a missing/wrong inner password. Mobile
loads comic metadata lazily so malformed XML does not block otherwise valid pages;
its native metadata form shares existing field validation. Drafts and inner
passwords remain in session memory and are cleared with the private reader.

## Validation

`test_local_crypt.py` exercises actual desktop rclone mirror/read/save operations,
revocation, leases, cancellation, invalid mappings and failure preservation.
`mobile_build/rclone_bridge/localcrypt_test.go` covers real rclone cipher listing, exact
ciphertext copies, offline decrypt after remote removal, re-unlock, tampering and
unsafe backing rejection. `test_mobile_localcrypt.py` covers ciphertext bookkeeping
and portable RAM readers; `mobile_build/tests/transfers/test_localcrypt_ui.py` covers dummy-backend editing and lifecycle controls.
Host tests do not establish Android/iOS native runtime behavior. The native suite
also exercises desktop-generated ciphertext through real platform widgets and the
compiled bridge: reading, text/Markdown saves, comic/EPUB metadata saves with inner
AES passwords, stale-save rejection, draft retention and credential locking.
Oversize rejection remains a core test; feeding an oversized single line into the
Android text widget stalled its layout during native testing.

The disposable `document_storage_tools` runner supports `--probe localcrypt` on
iOS and Android to exercise this complete native LocalCrypt sequence separately.
Text-save acceptance checks the shared “Saved locally” status, clean draft state,
absence of plaintext sentinel bytes in the stored ciphertext, and decrypted
readback with the original encoding. The runner removes its owned QA app and
simulator/emulator after collecting results.

The desktop browser and mobile managed folder browser support decrypted names,
rename, permanent delete, mkdir and moves within and across encryption boundaries.
The commonUtils provider operations remain backend-agnostic; their API and failure
contract are documented in that repository's provider guide. Crypt adapters own
name mapping and stream encryption. Mobile managed trees live under
`LocalCryptFolders/<crypt-settings-fingerprint>` with only ciphertext names/data;
`LocalFiles` is their explicit plaintext counterpart. Existing UUID downloads can
be moved into either tree without migrating other copies. Remote cloud operations
remain read-only on mobile; no upload or folder mirroring was added.

`crypt_path` maps names using the loaded session and verifies the identity.
`crypt_raw_read` authenticates complete bounded files without unwrapping inner
archives. `crypt_raw_write` encrypts plaintext descriptors or rewraps authenticated
ciphertext from another crypt; it never writes a plaintext intermediate file.
Consequently moves preserve inner ZIP encryption byte-for-byte without requesting
an inner password. The production path uses streamed `crypt_raw_write` and range
reads without the old 32 MiB ciphertext cap. Name-looking plaintext
is rejected during reads/verified transfers; listing alone does not authenticate
file payloads. A same-crypt rename preserves bytes, including any pre-existing
corruption, and is not a whole-file integrity scan.

Text Save As stages/verifies before no-replace publication, then retargets the
editor; the original stays unchanged. Mobile supports Local and crypt targets from
both its ordinary text editor and private editor; desktop private Markdown uses an
optional generic storage callback. Existing saves retain revision checks, and local
mutations serialize with editor transactions. Native iOS folder selections reload
the pinned Toga 0.5.7 picker's row count after replacing its source, preventing stale
row indices. Shared UI code never infers encryption from names or silently falls
back to ordinary filesystem writes for a virtual path. Future consumers must use
the provider's complete save/move operations; raw filesystem writes remain outside
this contract.


The optional host bridge integration test is
`test_mobile_localcrypt_native.py`; set `LOGISTICS_MOBILE_BRIDGE` to a compiled
host shared library to test desktop ciphertext through mobile text/comic/EPUB
saves. Native Go tests cover AES and ZipCrypto preservation, authentication,
unchanged raw member bytes and cancellation. Dummy-backend UI tests cover metadata
drafts, failure retention and clearing. Device UI validation remains separate.

## Shared resource refactor

Desktop text/archive saves and mobile private text/metadata saves delegate the
transaction sequence to commonUtils. Logistics retains ciphertext staging, session
checks, native/CLI calls and inner-archive verification. Desktop text saves compare
the decrypted staged bytes before publication. Mobile verifies that the staged
ciphertext remains unchanged during verification and reports a published save
explicitly if refreshing its revision fails.

The desktop Markdown adapter uses the editor's public save lifecycle. Mobile local
text uses a small text presentation adapter over shared text state, independently
of the comic/EPUB reader. `CryptTransferStream` is a Logistics-owned scoped adapter
for native rewrapping; commonUtils sees only its logical binary stream. Consumed or
closed transfer sources are rejected. Crypt names, keys and descriptors do not
enter the shared provider contracts.

Provider capabilities distinguish a complete folder backend from an existing
single-file offline download. Moves report verified destination publication and
incomplete source cleanup separately; UI messages tell users to refresh before
retrying. See commonUtils' own provider guide for shared interfaces and module
ownership rather than duplicating that API here.

## Provider bypass audit (2026-10-13)

Desktop and mobile provider browsers now call complete shared operations for
rename and folder creation, including capability and cancellation checks. Ordinary
comic and EPUB metadata writers use the same shared verified publication
transaction as provider-backed metadata; their local backup/permission policies
remain domain-owned. Private metadata continues through its crypt adapter and
retains inner archive passwords.

Logistics registers the configured LocalCrypt root for ordinary desktop storage
access, and registers each actual backing root when a connection is published or
opened. Shared raw-filesystem operations reject those roots and recursive ancestor
operations. This closes ordinary editor Save As, clipboard transfer, inline/bulk
rename and deletion routes into ciphertext storage without teaching commonUtils
about encryption. Internal connection records use a narrowly scoped backend grant.
The protection remains in place after locking; arbitrary external tools and direct
third-party filesystem calls are not sandboxed by it.

Desktop text and Markdown Open/Save As now use the shared resource browser
selection model. Logistics supplies local roots, configured crypt connections,
unlock prompts and provider leases through `services.documents.ui.editors`.
Private text windows own only memory buffers; private Markdown retains its
memory-only resource loader. Worker completion precedes provider release and
window retirement. The native mobile chooser uses the same selection validation
with Toga widgets and app-managed Local files roots.

Ordinary text-to-crypt handoff excludes the draft from future checkpoints and
queues recovery removal after pending writes, including a claimed recovery file.
Publication waits for that removal. A failed handoff keeps the draft in memory
and requires explicit Save/Discard/Cancel on desktop; mobile retains its draft
until saved. Successful mobile handoff resets both the source document and hidden
editor widget to the original baseline. Historical plaintext files, system
backups and process memory are outside recovery cleanup guarantees.

Mobile Save As prepares the new reader before discarding the old draft. A verified
save followed by a reopening failure reports that the destination exists and keeps
the original editor draft and Save As buffer. Backend staging, app-private document
records and downloads intentionally retain their storage-specific mechanisms;
they are not UI shortcuts around provider operations.


## Push preflight

`validate_localcrypt_push` retains the mutation lock, source/root identity checks,
provider operation and final cleanup verification. `_remove_plain_generated_files`
names only the existing allowlisted raw-file cleanup; `_authenticate_contents`
runs the existing bounded hash/download verification inside the caller's provider
operation. Name inventory, content authentication and encrypted-junk deletion
retain their original order. Helpers introduce no credential or cancellation owner.

`features.rclone.transfers.sync.rclone_sync` routes existing local-to-remote sources through
`push_policy` before launch, including secondary feature callers. Personal push
exclusions are separate from the fixed generated-junk deletion allowlist. LocalCrypt
preflight holds the shared mutation lock, rejects links/special/hard-linked entries,
removes eligible raw generated files, compares physical inventory to decoded
provider entries and streams a downloaded SHA-256 pass through rclone's crypt
reader. Hash output stays in RAM. Header checks alone are never accepted as proof
of encryption; every file must authenticate, and before/after inventory/root
identity must match. `no_data_encryption` cannot pass. Configured root links remain
supported; links below that boundary are rejected. No filters apply to validation. The same fixed basename allowlist also recognizes
encrypted generated files in decoded listings. After authentication and stable
inventory checks, `delete_resource` removes those files with their captured
provider revisions. Directories are excluded from cleanup; custom filters cannot
expand it. A final inventory verifies remaining files and directory identities,
allowing only directory timestamp/size changes caused by child removal.

The GUI waits through a cancellable worker dialog; validation failure or late
cancellation prevents transfer launch. Source changes during validation fail.
External filesystem changes after preflight remain outside an atomic snapshot
contract; do not edit the raw copy while pushing. Pushes continue using ciphertext
mirroring and therefore user rclone patterns match stored (encrypted) names.
Exclusions are never interpreted as cleanup patterns and `--delete-excluded` is
not used. Dry-run/query paths do not delete generated files.

Editor picker native evidence is retained in
`test-results/mobile-evidence/2026-10-13-editor-picker-{ios,android}-native-ui-local.json` for
source SHA-256 `c38cd17da93fcaf9ec510170dccf8bc768e125573bc4adf92ea603f91c9dcb6b`.
Both platforms passed all 15 native case groups; file management also exercises
decoded editor Open, Save As, active recovery cleanup and hidden widget reset.
These are local simulator/emulator checks, not physical-device or release evidence.


## Follow-up provider and editor audit

Drive-root Local picker providers can now transfer individual items into or out
of nested LocalCrypt storage. Overlap checks use the providers' actual item
locations, retaining namespace, protected-path and self/descendant protections.
Markdown link routing follows the active storage after Save As and carries anchor
fragments to the opened document.

Mobile reader handoff builds the replacement widgets before clearing the old
reader or draft, and commits only after navigation succeeds. A prepared private
Save As handoff bypasses the ordinary draft checkpoint gate because that draft
has already been removed from recovery and is still held in memory; successful
handoff then resets the ordinary document and widget. Native evidence explicitly
asserts that the replacement editor is visible. Construction/navigation failures
retain the original reader and draft. General view replacement restores the
previous view if attaching its replacement raises an exception.

Follow-up native evidence: `test-results/mobile-evidence/2026-10-13-final-audit-{ios,android}-native-ui-local.json`, source SHA-256 `66ebad8e3c280532411053031e140675088baa5808d7e534d6b5cb64326cb4bd`. Both simulator/emulator runs passed all 15 groups. Desktop/provider/native-bridge regressions passed 50 tests; mobile UI failure tests passed 11 tests, and the Go bridge suite passed.


## Shared save handoff consolidation

Desktop provider text sessions, ordinary-editor-to-private handoffs and mobile
Save As now share the generic publication/reopening lifecycle in commonUtils.
Each Logistics adapter still constructs its own reader and verifies reopened
bytes before replacing its draft. Mobile Save As now rejects a concurrently
changed destination instead of accepting its new contents as the saved draft.
Encryption, credential lifetimes, inner ZIP passwords, archive rewriting, native
widgets and recovery policy remain in their existing Logistics owners.

Shared-handoff validation: 30 desktop/provider checks, 3 focused shared lifecycle checks and 11 mobile UI checks passed. Both native simulator/emulator suites passed all 15 groups for source SHA-256 `010cfbeed8df7931f309393e0b10a8a6127f64f0400283a30a756d2d4dbc085f`; reports are `test-results/mobile-evidence/2026-10-13-shared-handoff-{ios,android}-native-ui-local.json`.


### Regular browser navigation and Workspaces

The Logistics browser host owns LocalCrypt routing via the shared FileBrowser
`directory_handler`/`directory_boundary` callbacks. Navigation is consumed before
raw listing, index-scope changes or external activation. Redirects are deferred to
the next GUI turn, reuse a private workspace tab, and preserve the ordinary tab.
The model suppresses children below provider boundaries; no crypt logic lives in
commonUtils. Unknown mappings fail closed. Raw deep paths open the copy root;
trusted private-tab cloning preserves the decoded directory instead. Credential
unlock cancellation leaves the existing locked-view retry workflow intact.
The desktop inline unlock form names the selected workspace. The host hides the
Actions dock while Files needs credentials, retaining its previous vertical split
for restoration after unlock or selection changes. Plain Local copies keep their
browser and use the Actions unlock form when only remote tools need credentials.

rclone sources omit the extra saved-copy source when the loaded account source
already represents that exact connection. Distinct Local and LocalCrypt copies
remain separate, and Workspaces adds short storage labels and full tooltips.


Workspaces source construction snapshots ordinary folders and LocalCrypt mappings
once per rclone refresh, shared across all account sources and duplicate detection.
Qt's repeated model queries use a bounded one-second host boundary cache, avoiding
repeated configuration reads and path resolution during painting. Explicit
navigation still resolves fresh; cached mappings refresh on publication and at
least once per second. Only connection identities/boundary decisions are cached,
not decrypted filenames or credentials.

### Private desktop presentation

Private browser view titles and document window titles begin with `🕵️ Private - `; the document host inherits these titles for its tabs. Text and Markdown refresh the prefix through their normal dirty/save title lifecycle. Comic reader and metadata titles use the source privacy flag. Browser detached titles place the view title first. The shared provider browser reuses the regular list/tile/column presentation, navigation icons and breadcrumb drawing, with generic folder icons that never inspect virtual paths through QFileInfo. Picker storage selection and provider worker/lease ownership remain unchanged.

Workspaces filters private folder contributions before running availability detection. LocalCryptFolder declares its private storage boundary, and rclone explicitly opts into the private-folder tool contract, retaining encrypted Pull/Push/browse without invoking local-only detectors on ciphertext.

### Reader picker handoff

`services.documents.ui.readers` reuses the editor resource catalog with EPUB/CBZ filters and the current folder. Ordinary selections preserve local reader navigation; private selections prepare a source-backed EPUBBook or ComicPages on a cancellable worker before presentation. The modal loading dialog preserves the document launcher’s creation scope and waits for worker retirement before returning. Cancellation and failed opens release the choice; successful readers retain it until destruction, including inner-archive password retries. Reused comic readers release the redundant choice. Private EPUB readers skip ReadingState construction and recents, retain bookmarks only in RAM, and use the existing encrypted metadata adapter. Main-window shutdown also cancels and waits for its registered resource jobs.


## Shared mobile browsing and streaming

Automatic mobile credential loading uses `CloudUI.prepare_cloud` and the shared
`start_cloud_restore` task. These initialize the client, restore protected
credentials and prepare folder identities without constructing browser/settings
controls. Workspaces' Cloud source uses the same model task. `show_cloud` builds
the remote UI on demand, preserves the credential generation and busy state, and
publishes already loaded names without restoring again. The retained-package
settings list is built on its first visit; subsequent credential/busy updates
still refresh it. Credential document-list publication skips an unopened Documents
page while continuing to refresh Home icons. Encrypted-folder discovery validates
the collection base once per scan rather than once per remote.

The native host uses commonUtils' portable browse snapshots and Toga list/tile
presentation for Local files, LocalCrypt, remote listings and the editor picker.
Logistics retains storage selection, credentials, navigation and mutations.
Local and LocalCrypt folder listings do not register thumbnail callbacks in
either List or Tiles mode. Merely displaying, sorting or searching names does
not open archives, inspect covers or decrypt file contents. Explicit information
selection can use the metadata callback; file taps open their reader directly.
Clearing credentials stops browsers and clears decoded labels and details.
Crypt ciphers are cached in memory by encryption settings, independently of each
remote's connection identity and backing path. Cache fingerprints normalize
rclone-obscured password/salt spellings; password, salt and filename settings
remain part of the key. No fingerprint or derived cipher is written to disk.
Vault/ZIP validation uses a private candidate cache, sharing one derivation across
the envelope and its packages. Missing distinct configurations are prepared by
up to four workers, bounded by Go's available parallelism. Workers use independent
results rather than concurrently mutating the candidate map, and a failed batch
publishes none of its results. The cap bounds simultaneous scrypt working memory
to approximately 64 MiB; rclone's derivation parameters and saved format are unchanged.
Successful publication carries those prepared
ciphers into the active cache and retains only settings referenced by admitted
credentials. Failed validation/publication leaves the active cache unchanged.
Folder discovery and LocalCrypt reads reuse the prepared ciphers without changing
their existing connection-identity checks. Automatic restore takes crypt names and
local directory fingerprints from the published credential records, avoiding a
second native query and one native identity call per folder. Alternate adapters
without those fields keep the native-query fallback. These fingerprints are local
discovery metadata; opening/decrypting still validates native admission and identity.
Unchanged saved-package associations do not rewrite preferences. Lock clears the active cache; replacing
credentials removes ciphers no longer referenced by any loaded package.
`crypt_cipher_cache_test.go` covers reuse across 16 separately obscured remotes,
vault restoration, failed/changed credential replacement, lock retirement,
encryption-option separation, parallel/sequential encryption equivalence, batch
failure atomicity and concurrent filename reads.

`CryptFiles.list` enumerates direct children with `scandir`, checks each child's
link/type/independent-file constraints, and validates the parent/collection at
both snapshot boundaries. It decodes only basenames in batches of at most 256,
then appends the already-validated logical parent. Decoded names containing a path
are refused. A second no-follow stat rejects entries replaced during decoding;
revision tuples and modified times remain available for sorting and later
operation checks. It shares the fast local-offset timestamp formatter with
`CollectionFiles`. None of these listing steps reads document bytes or contacts
the backing remote.

An isolated macOS host benchmark using the real native bridge measured 1,000
synthetic files at about 39 ms for Local and 17 ms for LocalCrypt, down from
72 ms for the previous LocalCrypt listing. This excludes native UI construction,
credential import and device/SD-card latency; it is not an Android timing claim.
`test_mobile_folder_listing_native.py` verifies real nested filename decoding,
batch boundaries and locked-session rejection. Mobile tests also cover zero
content/thumbnail calls, invalid decoded paths, cancelled listings, links,
hardlinks, special files and parent replacement during decoding.

Descriptor-backed downloads and crypt moves stream bytes. Local archive preview
and reading seek encrypted ranges, decrypting bounded members on demand. Native
metadata rewrites authenticate members as streams, copy untouched compressed
entries, and encrypt output through a pipe into exclusive ciphertext staging.
The host compares streamed resource manifests before publication. Transfer/rewrite
operations allow 30 minutes, while network inactivity remains bounded at 15 seconds.
Whole-file legacy byte-returning helpers still have memory buffer limits and are
not used by production mobile crypt reads, moves or downloads.

## Windows session and storage portability

Session-only desktop crypt commands use `NUL` on Windows and the platform null
device elsewhere; rclone requires Go’s exact Windows spelling to avoid attempting
to open a configuration file. Storage migration normalizes Windows extended-path
prefixes before comparing and rebasing link targets. Protected-key records reject
links explicitly even on systems without `O_NOFOLLOW`, and compare the opened
file identity with the inspected record before decoding it.

Private archive rewrites use the shared binary subprocess writer’s explicitly
nonseekable sink. This prevents Windows pipe seek behavior from corrupting ZIP
member offsets while streaming comic and EPUB metadata to rclone. Verification
still completes before publication, preserving the original on failure.

## Mobile sync progress and copy names

### Local reading during folder transfers

Local crypt reads use a credential read scope independent of the bridge's serial
network-operation mutex. Path decoding, stat/range reads, archive inspection,
manifests and thumbnails can proceed during a managed folder transfer. Each has
an independent deadline and does not replace the transfer cancellation handle.
Credential import, replacement and clear take an exclusive scope; cipher-cache
publication is separately synchronized. Online operations and local crypt writes
remain serialized with the transfer.

Workspaces and Files permit LocalCrypt browsing and private document opening
during transfers. These providers are offline reads even though they require
unlocked keys in the native bridge. Browser cancellation and private-session
cancellation remain independent of transfer cancellation. Listings omit rclone's
`<name>.<8-hex-hash>.partial` objects and tolerate entries removed during listing;
range/archive revision checks still reject files changed during reading.
File-management mutations remain unavailable while a transfer runs. The same
offline-read policy covers Documents and library shortcuts; private rows and
opens are bound to the current client and credential generation. Encrypted source
discovery and reader-store construction are feature-owned adapter functions.

The embedded `mirrorSync` uses rclone accounting scoped to its transaction ID.
Mobile Pull creates missing destination folders and downloads missing local files,
including after proceeding without a full review. Its Python filesystem checks
tolerate destination entries removed between listing and metadata inspection;
missing collection roots, permission errors and unsafe links still fail. Push
inventories remain strict because local files are the upload source.
The native preflight also tolerates confirmed missing destination descendants
on Pull. If Android removable storage returns `readdirent` ENOENT for a directory
that still exists, it retries that directory's complete link validation once with
a fresh directory read. A second failure, missing root, permission error or unsafe
link still stops the scan. Push does not relax its source checks.
`mirror_progress` returns transferred/total known bytes, completed/total known
files, active transfers, listed entries and checks. It publishes a final snapshot
before resetting the accounting group. It also reports attempt/max-attempt counts
and retry-wait state. Sync uses rclone defaults and operation-scoped accounting
for CLI-style high-level retries, including read-only reviews. Waits are
cancellable; Sync and review have no fixed overall deadline. Each comparison
attempt clears its rows and revisions. Shared review state atomically replaces
progress snapshots; the native polling thread retires before publishing final
rows and cleanup, preventing late progress from overwriting the final result.
The desktop adapter resets rows at CLI failed-attempt boundaries too. Failed or
cancelled comparisons remain incomplete and never authorize execution. Python forwards those counters without
substituting zero file counts. The UI distinguishes discovery, transfer and final
checking, shows activity when totals are unknown, and changes animation mode only
when a known byte or fallback file total appears or disappears. Details and the
banner display a numeric percentage of known work, preferring bytes over file
counts. The controller retains `transfer_percentage` when details are reopened
and resets it for each new run. Live values are capped at 99%;
only the sync result and subsequent local verification establish completion.

New managed copy targets keep the remote's spelling, or the selected plaintext
subfolder's name. LocalCrypt target labels use the remote name without storing a
decoded private subfolder title; its physical account-identity scope is unchanged.
Case-insensitive mapping conflicts are refused. Existing exact-name plaintext
folders can be adopted by an explicit pull, retaining the prior destination-sync
behavior. Generated UUID suffixes on existing mappings are removed at the next
pull; plaintext directories move without replacement, while crypt storage stays
in its existing scope. A failed record publication rolls back the directory move.
Migration refuses occupied destinations. Existing arbitrary target names remain
readable. `test_mirror_jobs.py` covers forwarding, display transitions, naming and
conflicts; the embedded bridge suite exercises throttled crypt pulls in both
plaintext and ciphertext modes and verifies live counters and downloaded bytes.

### Mobile transfer approval

The mobile Files selector opens source-specific folder actions. New-copy and
mapped-copy Pull writes require a native OK/Cancel confirmation; reviewed Push
requires another native confirmation at the final write boundary. Cancellation
leaves the destination unchanged. The UI checks captured connection generation
and mapping/plan identity again after approval, so changing credentials or targets
while the dialog is open cannot authorize an old transfer. The existing rclone
Sync scope and comparison rules are unchanged.

## Security audit and session hardening (2026-10-15)

Scope: desktop credential sessions, private browser/editor/reader handoffs,
provider/range/thumbnail caches, mobile native crypt/vault operations, offline
records, private sessions, preferences and iOS scene lifecycle. This is a source
and regression audit, not a penetration-test certification.

Confirmed issues corrected:

- Desktop `CryptResources.open` now supplies a RangeReader validator. Previously
  the reader's own cached blocks bypassed credential revocation, cancellation and
  physical revision checks. Validation now runs before cached reads and seeks.
- Credential generations have weak revocation observers. Revoking/replacing a
  parent closes its providers and clears their decrypted caches. Desktop private
  browser, editor, reader and metadata windows retire on revocation, replace their
  titles and refuse to become visible again. These windows must be reopened.
- Mobile session-only imports retain original password-protected ZIPs through
  `CredentialPackages` under device encryption. Package/remote associations stay
  in its index, while ZIP passwords and decoded credentials remain in memory.
  Preferences filter session-only associations before every write and on reload.
  Unencrypted ZIP retention is rejected.
- Mobile credential generations now cover the whole process, matching the native
  bridge's shared store. Replacement through another client invalidates native
  source caches and retires stale reader views. Ordinary local provider sessions
  remain independent of credential generations.
- iOS windows with a privacy gate receive an opaque interactive shield
  synchronously on resigning active, before background snapshots; scene callbacks
  cover independent windows. Inactivity, including an unattached startup scene,
  and capture signals alone never shield a window without a gate. Clearing the
  last gate removes an existing shield even if those signals remain active.
  Active recording/mirroring is observed through the scene capture trait on iOS
  17+ and UIScreen capture notifications, with the legacy signal on older systems.
  The shield also dismisses the keyboard. Android applies FLAG_SECURE while
  session-only credentials or their associated private views exist.

### Mobile resume lock (October 15, 2026)

`CloudClient.session_privacy` follows the process-global native credential store.
Only successful session-mode imports/additions create a memory-only resume gate;
failed imports preserve the existing gate, and saved-vault opens/clears remove it.
Private controllers and collection batches retain the gate they were opened with,
so clearing credentials alone cannot remove protection from retained private views.
Ordinary local provider views and saved credential packages do not enable privacy.
An explicitly supplied private archive password creates its own resume gate.

`ScreenPrivacy` covers the complete window on inactivity and replaces the entire
navigation root with a password screen. Routes and worker completions may update
the retained navigation tree but cannot reveal it through the lock screen. UIKit
scene/app notifications and Android activity pause/resume callbacks lock before
returning control to the OS. Foreground activation never unlocks a gate. Resume
verification runs off the UI thread, checks gate identity and lifecycle revisions,
and restores navigation only after every remaining gate is unlocked. A renewed
background transition or credential replacement invalidates an in-flight unlock.
Private drafts stay in RAM. Passwordless sessions require a confirmed temporary
password before access. Salted PBKDF2-SHA256 verifiers (200,000 iterations) stay in
RAM only; they do not reload credentials or persist passwords.

iOS scene-capture traits and legacy screen-capture notifications still conceal
the complete window during recording/mirroring. Non-application scene roles get
a picture-only external-display window without constructing a workspace or loading
its catalog. It displays ordinary visible comic artwork only when no privacy gate
exists anywhere in the process. Loading session credentials or retaining protected
views clears the external image, including after unlock; without a comic it is black.
It does not disable AirPlay itself or prevent iOS still screenshots. Physical
AirPlay and OS lifecycle enforcement require device validation; mocked policy
tests do not establish those platform guarantees.

The isolated native probe passed on an iOS simulator and Android emulator with
the source fingerprint recorded in the iOS result (local artifact `test-results/mobile-evidence/2026-10-15-session-privacy-ios.json`)
and Android result (local artifact `test-results/mobile-evidence/2026-10-15-session-privacy-android.json`).
It checks credential-load activation before a view opens, a real switch to
Settings and back, wrong/correct resume passwords, preserved unsaved edits,
Save As draft protection after credentials are cleared, and final protection
release after the remaining view closes. Android also checks FLAG_SECURE on/off.
The returned lock screens are recorded for iOS (local artifact `test-results/mobile-evidence/2026-10-15-session-privacy-ios-locked.png`)
and Android (local artifact `test-results/mobile-evidence/2026-10-15-session-privacy-android-locked.png`).
These checks do not validate physical AirPlay, all capture routes or frame-by-frame
OS snapshot timing. The focused host regression run passed 63 tests. The broader
mobile run has an unrelated library-label expectation failure; loopback fixture
tests blocked by the sandbox passed when rerun with local socket access.

### Boundaries that still matter

"Session only" means the current application process. Mobile background locking
preserves unsaved RAM edits and credentials behind resume authentication;
navigation within the app does not lock it. Revocation retires private
views and prevents further reads, but Python/Qt/Go and OS memory management do
not promise secure memory erasure, protection from a compromised process, swap,
crash dumps or a privileged local attacker.

No application plaintext thumbnail cache, document history, reading-position file
or recovery record was found in the reviewed LocalCrypt reader paths. Providers
and previews use RAM; mobile private workspace sessions are excluded from saved
workspace and recent-document records. Explicit decrypted download, Move to Local,
Save As to Local, clipboard copying and exports intentionally publish plaintext.
They are outside ciphertext-only storage.

LocalCrypt honors the source rclone crypt settings. `filename_encryption=off`
leaves filenames visible; `directory_name_encryption=false` leaves directory
names visible. Obfuscated names are not cryptographic name protection. Do not
claim name secrecy without standard filename and directory-name encryption.
Remote names, credential-package paths/names, connection records, ciphertext
sizes/counts/timestamps and local root names are not all encrypted. Desktop rclone
command arguments can contain decrypted relative paths and child-process private
environments contain keys. Session mode does not hide these from a same-account
process inspector or administrator. Saved credential mode intentionally persists
recoverable credentials; switching to session mode does not erase an earlier
saved config/vault or the user's source credential ZIP.

Apple exposes no general supported API to disable still screenshots. Its
[screenshot notification](https://developer.apple.com/documentation/uikit/uiapplication/userdidtakescreenshotnotification)
arrives after capture. The shield addresses
[background snapshots](https://developer.apple.com/library/archive/qa/qa1838/_index.html)
and responds to [active capture](https://developer.apple.com/documentation/swiftui/protecting-sensitive-content-when-screen-sharing).
It cannot guarantee that the first frame of a recording never contains content,
block a camera, or delete a screenshot already taken. Android's
[FLAG_SECURE](https://developer.android.com/security/fraud-prevention/activities)
is a platform capture control, not a defense against a compromised device.

### Verification for this audit

- 222 mobile host tests passed, including mocked native screen-state transitions,
  secure-window flags, session-label migration and displayed plaintext retirement.
- 54 desktop/core LocalCrypt, cloud, mobile-reader and file-operation tests ran:
  51 passed and 3 optional native-bridge tests skipped without the host library.
  All 4 desktop credential-session tests passed separately.
- The iOS 27.0 iPhone simulator passed all 27 native UI cases, including private
  reading/editing/metadata, revocation, file management and direct shield
  conceal/reveal. The captured covered UIWindow is entirely black and foreground
  recovery was verified. Native report (local artifact `test-results/mobile-evidence/2026-10-15-localcrypt-security-ios-native-ui-local.json`)
  and shield image (local artifact `test-results/mobile-evidence/2026-10-15-localcrypt-privacy-shield.png`).
  The local source snapshot is `051f545d7d49c74ec83a3974c9acc747ef3f6e16fc877f0e395b22779ad18a5f`.
- Ruff and diff whitespace checks passed. Android capture enforcement, physical
  iOS app-switcher snapshots, actual recording/mirroring transitions and iPad
  multiwindow native behavior were not verified in this run. Still-screenshot
  prevention is not claimed. The screenshot above is a direct UIKit window
  capture while explicitly concealed, not proof of every OS capture path.

### Easy-access follow-up

Session-only imports retain original password-protected ZIPs under device
encryption for future password-only unlocking. Decoded credentials and passwords
remain in memory. Credential-package tests cover retained ZIP recovery, Settings
autosave isolation, wrong-password retry and unencrypted ZIP rejection.
Existing saved vaults remain until explicitly forgotten. The native report above
predates this follow-up; its screen and revocation protections are unchanged.

## Mobile Workspaces visibility and Settings unlocking

Workspaces uses `CloudUI.loaded_remote_names` for Cloud destinations. Retained ZIP
metadata identifies local copies and encryption types, but does not create online
rows. Existing physical mirror targets remain visible locally while locked or
forgotten. Matching package and connection identities keep same-named accounts
separate; a local mapping cannot manufacture a remote destination.

Settings lists retained and loaded packages as archive rows. Each package page
shows its status, password, Unlock action and its own Loaded remotes. Unlock opens
`CredentialStorageDialog`, which uses the shared desktop retention explanations.
Cancel changes no credentials. Session-Only and persistent loads share the native
publication path. The first page retains session locking and troubleshooting.

`NativeCredentialForget.package_name` selects one package; `None` removes all.
The bridge's `forget_package` action erases the selected saved snapshot, including
an older saved version hidden by a session import, and revokes its active context,
resume gate and document-list key. A locked saved vault is read without loading
its other packages. Other package aliases, modes and token stores survive.
`CredentialPackages.forget_package` removes the retained ZIP and encrypted lists
and publishes the new index to other scenes. Both visible removal actions confirm
before mutation; all-credential removal uses a severe warning. Session locking
keeps saved material and retained ZIPs; neither removal path deletes local folders.

Host tests cover package navigation, all retention choices and cancellation,
scoped forgetting, shared retained indexes and local-only discovery after removal.
Go tests cover saved/session isolation, shadowed saved copies, locked-vault removal,
last-package deletion and persistence failure. Native phone layout still requires
device validation after these changes.

Package removal takes the package mutex before the shared saved-vault mutex,
matching OAuth token-save callbacks. The parent lock is released before publishing
the remaining contexts. Known document-list caches are erased independently of a
retained-package index failure, with partial failures reported for retry. Folder
rendering reuses one loaded-remote snapshot when building credential filters.

Historical validation (2026-10-15, before retained online-only rows stayed visible):
225 mobile host tests passed, including the no-local-folder Settings
unlock, wrong-password retry, remote-only visibility after unlock, and retaining
an existing LocalCrypt copy after session lock. Eight cloud/vault core tests
passed, including confirmation that session lock never deletes the saved vault.
All 28 iOS simulator UI cases passed with real native widgets and the compiled
bridge; the new credential-visibility case checks Settings unlocking, wrong
passwords, hidden locked remote-only actions and preservation of saved ciphertext.
Native evidence (local artifact `test-results/mobile-evidence/2026-10-15-folder-hub-credential-visibility-ios-native-ui-local.json`).
Ruff and diff whitespace checks passed. Android native runtime behavior was not
rerun for this change; its Workspaces and Settings controller code is shared.

The old native per-file mirror list/read/stat/mkdir/write operations are retired.
Test fixtures seed and inspect synthetic remotes with `mirror_sync`; backing
filesystem access in Go tests is test-only. `mirror_validate` is retained for
crypt authentication and version checks before Push, along with independent
regular-file descriptor checks (zero offset, one link, no pipe/directory).
`privateOutput` and the scoped document/crypt APIs retain their existing guards.

### Completed final consolidation items

See the [current rclone record](rclone-parity.md#current-audit--2026-10-15) for
validation and retained platform boundaries. Desktop hashed-layout compatibility
is removed, and desktop/native engine pins are aligned on 1.74.1. Desktop review
adds directory membership/type rows with decoded names, including encryption-off
and directory-name-encryption-off settings; directory timestamps do not invalidate
an otherwise unchanged review. `mobile/previews.py` now owns native crypt source
construction and encrypted thumbnails; the app keeps generic preview orchestration.
Crypt authentication, staged-save verification, link/hard-link rejection and
independent regular-file descriptor requirements remain in place.

## Markdown opening modes

Private desktop browser activation captures Alt/Option before asynchronous loading
and defaults to preview. Explicit editor choices retain editing through the
`edit` argument; following Markdown links requests preview. Mobile provider sessions
use the feature-owned formatted Markdown input and the existing source buffer,
with one visible surface in preview, Formatted or Source mode. Suspending a private
session retires its formatted WebView and restores its selected mode on resume.

## Recursive filename search

Desktop CryptResources supplies search_entries using one recursive encrypted
lsjson listing per query, with cancellation and a 64 MiB output bound. It checks
the physical subtree for links and special files before listing and retains
decrypted mappings in RAM. Output overflow fails visibly. Mobile CryptFiles
decodes each listed child once and constructs metadata from its known physical
entry, avoiding repeated native re-encoding calls. Shared browser search waits
400 ms after the last edit and visits the full subtree by default; the former
10,000-entry scan cutoff no longer hides matches in large collections.

Desktop `create_file` streams input through the shared complete-copy contract.
Would-block reads are errors rather than EOF; failed input cannot publish an
empty/prefix ciphertext file. The existing command error and owned-stage cleanup
paths remain responsible for reporting and retirement. No plaintext staging is
introduced.

Mobile inputs without a file descriptor use bounded complete reads before native
encoding: short reads continue, would-block input fails, and the existing 1 MiB
limit is checked after reading at most one extra byte. Failure removes only the
owned encrypted staging file and never publishes a truncated prefix.

## Service composition and resource sessions

`features.rclone.service.RcloneService` retains credential, remote, LocalCrypt and
transfer services. The desktop composition is `desktop_service.service`; native
clients retain theirs through `mobile.service.native_service(client)`. Native
credential policy is in `mobile/credentials.py`; `mobile/service.py` only wires the
adapters. Managed-tree and offline-copy references belong to
`localcrypt/mobile/locations.py`. The services do not own widgets or navigation.
Desktop password prompts and native credential import/vault workflows publish
through their platform authorities, sharing the existing credential registry.

`CredentialService.capture` returns a grant tied to the currently unlocked
generation, without exposing credential values. Locking revokes that generation;
reloading identical keys never revives the old grant. Desktop locking addresses a
package session; native locking explicitly reports its current all-package scope.
Locking retains saved credentials, credential ZIPs and ciphertext. Explicitly
reopening a saved desktop config can create new access using its saved credentials.

`LocalCryptService.open` creates an independent provider session. Desktop
`CryptResources` retains its existing child credential context, private caches and
resource leases. Native `CryptFiles` composes `ResourceAccess`, which owns its
closed state, grant validation, worker cancellation scopes and leases. Native
listings validate the grant before publishing rows, including empty folders.
Fallback buffered streams validate access on reads and seeks; native streaming
sources retain their existing generation checks.

Browser navigation and selection remain with the existing Qt resource browser and
mobile browser/listing owners. A mobile browser retains a provider lease until it
changes providers or stops. Reader/editor stores open independent access to the
same copy, so closing the browser does not close an already-open document.
Reopening a closed provider is permitted only within its original credential
generation; credential replacement requires a fresh explicit open.

Desktop Settings exposes **Lock Package** and **Lock All Session Credentials**.
The presentation host checks affected private editors and busy operations before
requested locking. Save must complete before retrying a lock; Cancel preserves
access. Unexpected credential revocation still retires views immediately. Mobile
retains its existing all-private-reader busy/dirty guard before locking connections.

Focused regression owners are `Python/tests/resources/test_rclone_services.py`,
`test_local_crypt.py`, and `mobile_build/tests/transfers/test_localcrypt_access.py`.
They cover unrelated packages, independent browser/reader lifetime, replacement
with identical keys, revocation during listing and requested-lock edit vetoes.

## Notebook resource editing

Notebook creation, opening, Save and Save As use the shared document resource
boundary on desktop and mobile. Private notebook drafts do not enter ordinary
recovery, history or saved workspace records. The binary buffer bridge accepts
bounded RAM input and writes only exclusive ciphertext staging; legacy text
encoding retains its text-specific limit. Mobile source/configuration text in
managed crypt folders uses the same verified resource publication boundary.
See [document storage and action parity](../../../development/document-storage.md)
and the [notebook owner](../../notebooks/development/development.md).
