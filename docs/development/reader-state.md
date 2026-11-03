# Private reader state and history clearing

Session-only remote sources (encrypted or ordinary) and LocalCrypt use the owning
credential ZIP password for persistent reader state. `services/documents/credential_state.py`
provides the bounded shared store. EPUB, comics, PDF and video adapters supply
format-specific positions; provider readers also retain their page, EPUB offsets
and bookmarks. Passwordless sessions keep state in RAM only. No fallback writes
private positions with just a device key, remote settings or storage encryption.

Desktop credential publication retains a separate mutable copy of the ZIP password
in the credential session registry. Derived remote/LocalCrypt contexts inherit the
active parent's authority. Revocation clears that key before notifying dependents.
This password is not part of credential settings, subprocess environments or saved
configuration. Mobile reuses the existing native AES-256 ZIP document-list primitive;
its password keys exist only in the native credential session. Both stores use
keyed opaque filenames. Random lookup keys are kept in ZIP-password-encrypted
`ReaderKeys/positions` and `ReaderKeys/bookmarks` records, so checkpoint names
cannot be tested by hashing guessed document paths. Password migration re-encrypts
these keys without changing checkpoint names. The stores also use source/document
bindings validated inside the ciphertext.
Offline-copy revision records may contain binary digests; the state envelope
binds those fields through SHA-256 so changed copy revisions reject old positions
without retaining the original binary fields in the envelope.

`ReaderPositions` and `ReaderBookmarks` are separate app-owned directories. Source
identity remains stable across ZIP repacking/password changes; encryption keys do
not. Existing unreadable/authentication-failed records are preserved and cannot be
overwritten with a new empty position. Lock/revocation checks still apply to reads
and publication. No state is restored solely because a ciphertext file exists.

## Password changes

Unlock the updated credential ZIP, then use the Reader history migration action
with the previous password. `state_migration.py` decrypts only in RAM, checks the
record's source against currently unlocked credentials, encrypts under the current
ZIP password, reads the result back to verify it and atomically publishes it.
Wrong passwords, changed accounts, corrupt records and revoked credentials preserve
the original. Existing current-password Recent entries merge with migrated history.
Changing both the password and source credentials can prevent automatic association;
unmatched ciphertext is retained, not assigned to a different account.

The previous password is not saved. Without it, old ciphertext remains unavailable
until explicitly cleared. Clearing positions also retires their lookup keys,
allowing fresh positions under the current password while preserving old bookmarks
for later migration. Mobile migration uses the existing bounded `file_archive`
bridge on the unchanged encrypted file; it does not extract a plaintext file or add
another crypto implementation to the native bridge.

## Clear actions and lifetime

`history_controls.py` backs separate desktop Reader history and mobile Reset settings
for clearing positions and Recent. Neither requires credential keys. Clearing
positions removes app-owned checkpoint files and advances a nonsecret generation
fence. Old readers and pending writes cannot recreate their pre-clear position.
Newly reopened readers can save new positions. Bookmarks, documents and Recent are
retained. Ordinary imported-library records have their location fields reset while
the document, metadata and bookmarks remain.

Clearing Recent covers loaded and unloaded credential caches and every scene's
ordinary history. Pending encrypted writes are retired under the cache I/O lock.
Legacy credential caches combine Recent and reopen references: unloaded reopen
references are removed too; loaded open references can be republished without
Recent entries. Active document instances and separately stored positions remain.

Old LocalCrypt video sidecars are upgraded/retired when their source is next
unlocked. A previous clear generation prevents their positions being restored.
Unloaded encrypted external folders cannot have individual ciphertext files removed
without their naming keys; the clear fence invalidates their old checkpoints and
physical cleanup occurs on next access. Old app-local remote video checkpoint
files are removed without decrypting them. Neither action promises physical secure
erasure from filesystem snapshots, backups or storage hardware.

## Verification scope

Host tests use real AES-256 ZIP encryption for wrong-password, tamper, revocation,
source isolation, clear fences and explicit password migration. A native-host
integration test exercises the actual mobile bridge for positions, bookmarks and
Recent across password replacement, migration and clearing while credentials are
unloaded. Provider opening tests cover preparation, restoration, publication and
retirement. Physical-device UI acceptance remains separate from these host checks.

## Local recent references after iOS updates

Loading ordinary Recent history resolves historical iOS application Documents
paths against the current registered Documents root before deduplication. Only
an existing relocated file qualifies; unrelated paths and missing files keep
their identities. Duplicate references retain the newest entry. New opens use
the same resolution, preventing a container relocation from adding a second row.
Secondary windows resolve against the app storage root while retaining their own
history file in the window settings folder.

## Favourites and desktop Recent

`services/documents/catalog.py` stores bounded file references and their opening
context. `DocumentCatalog` holds favourites; desktop `DocumentRecent` separately
holds ten recent references so clearing Recent preserves favourites. Ordinary
local references use JSON. Session-Only references use the existing desktop or
mobile credential-password AES ZIP cipher, with the credential identity checked
inside the encrypted envelope and access rechecked after transformation. They
are decrypted for display only while their credential is unlocked. Desktop landing
rows subscribe to revocation; mobile Home refresh follows credential publication.
Unreadable buckets are preserved and do not hide unrelated available references.
Focused catalogue tests cover wrong passwords, cross-credential substitution,
revocation during encryption, opening-method replacement and independent clearing.
