# LocalCrypt ownership and data flow

Logistics owns rclone crypt settings, credential sessions, ciphertext mapping and
transfer policy. commonUtils supplies backend-independent browsing, bounded binary
process I/O, range streams and Markdown storage hooks. Its
[provider contracts](../../../../Python/commonUtils/docs/development/reference/ui/resource-providers.md) are owned
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
including when saving a config. Validation completes in memory before saved-config or session
publication, so plain/mixed packages leave existing credentials intact.
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

`features/rclone/localcrypt/mobile/copies.py` reads existing UUID ciphertext copies
under app-private `LocalCrypt`, with an encrypted relative path, remote and
crypt-settings fingerprint. New folder copies use reviewed Pull and the mappings
owned by `transfers/mobile/jobs.py`; the former `crypt_fetch` action is absent
from the bridge contract.
No decoded filename or key is added to those records. The rclone settings determine
whether original filename encryption is enabled. Incomplete/invalid copies are
excluded. The fingerprint binds an offline copy to its crypt settings independently
of rotating backing OAuth tokens.

The production mobile reader uses `crypt_stat`, `crypt_range` and `crypt_archive`
over caller-owned ciphertext descriptors. A seekable shared RangeReader checks the
file revision and credential generation even on cached reads. Native archive
facades fetch authenticated members lazily; no whole decrypted ZIP view or
plaintext output file is created. `crypt_decode` remains a bounded legacy adapter. The native
reader/editor UI reads document bytes through the provider. Credential-bound
open/recent references are stored by `mobile/document_lists.py` in encrypted
per-package lists; these references do not create plaintext document copies.
EPUBBook accepts an optional generic archive source so portable reading can use
memory without a temporary file. Ordinary EPUB filesystem behavior is unchanged.

Mobile folder Pull/Push streams files to the selected Local or LocalCrypt copy.
Reader support includes text/Markdown editing up to 1 MiB, EPUB chapter text and
PNG/JPEG/WebP CBZ pages.
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
password; untouched entries retain their original protection. Saving edits updates
the local ciphertext only; uploading requires a separate reviewed Push.
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

## Push preflight

`transfers/push_policy.py` owns desktop ciphertext validation and generated-file
cleanup. Native `transfers/mobile/jobs.py` keeps execution admission and preflight
in `MirrorJobs`, delegating records, proposal resolution and engine polling to
separate owners. Neither a complete nor an incomplete review bypasses preflight.
Missing mappings, mismatched identities, changed ciphertext and linked storage
are refused before transfer. See [transfer workflow](transfers.md).

## Shared mobile browsing and streaming

`localcrypt/mobile/content.py` owns native content reads and verified writes.
`archive_source.py` supplies bounded seekable archive access; `resources.py` owns
virtual-to-physical mapping and the provider's resource session. Generic readers
receive provider capabilities rather than opening virtual cleartext paths.

Publication stages ciphertext, verifies the staged version, checks the original
revision and access grant, publishes and cleans staging. Closing or cancelling a
reader cannot authorize a late write or bind it to replacement credentials.

## Validation and history

Use `python3 dev.py test-owner rclone --mode fast` for the declared desktop and
mobile host suites. Real CLI tests use synthetic local/crypt backends when the
pinned executable is available. Native bridge tests and physical-device acceptance
are separate; host tests do not establish iOS or Android device behavior.

The [implementation history](history/history.md) preserves earlier audits,
streaming details and their original validation scope. Current owner entry points
are in the [developer guide](development.md).
