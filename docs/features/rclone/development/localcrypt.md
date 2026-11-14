# LocalCrypt ownership and data flow

Open an **Encrypted Copy** from Workspaces → Local and unlock its associated ZIP. Desktop `localcrypt/backend.py:CryptResources` and mobile `localcrypt/mobile/content.py:CryptContentProvider` expose virtual decoded paths. Keep physical I/O on ciphertext paths. [Shared provider contracts](../../../../Python/commonUtils/docs/development/reference/ui/resource-providers.md)

```sh
python3 dev.py test desktop --exact-file Python/tests/resources/test_localcrypt_transport.py
```

Expect ordered bounded batches, partial-response rejection and revocation. Real ciphertext uses pinned CLI and compiled bridge fixtures.

## Initial Pull storage choice

New session-only crypt remotes offer LocalCrypt (recommended) or Local. Saved credentials and non-crypt remotes create Local copies through review. Existing copies preserve storage type. LocalCrypt Pull mirrors the crypt backing target's ciphertext. Push resolves the same target for preview and execution, retaining encrypted relative paths. Edits stay local until Push. Mirrors can delete data and have no rollback.

## Desktop copy identity and migration

`localcrypt/mapping.py` binds schema-2 `.connections` records to absolute ZIP path and remote, under user application support `LocalCrypt/<remote-name>`. Refuse unsupported same-account mappings, case-insensitive ownership conflicts and untracked destinations; preserve existing ciphertext. Root relocation links are allowed; inner links and hard links fail. Moving a ZIP changes identity.

`localcrypt/connections.py` stores schema-1 associations for decrypted `Server/Local` copies in `Connections/Local`. Publish after Pull acceptance; partial GUI jobs retain the association for retry. Reject conflicting ownership before launch. `storage.py` migrates legacy `Server/LocalCrypt` and `Server/.local-connections` without clobbering. Cross-filesystem migration verifies staged hashes and rebased links before removing originals. On failure keep the source; reopen readers after relocation.

## Desktop private reads and saves

`CryptResources` builds process-private CLI settings and validates the ciphertext tree at construction/preflight. Listings recheck selected directories; range caches stay in bounded provider RAM keyed by revision. `CryptCommand` owns bounded output and subprocess cancellation. Revocation or replacement invalidates old providers permanently; reopen after unlock. Separate tabs and readers hold leases and the last release retires private credentials. Abandoned opens release staged media after workers retire. rclone child environments contain keys, and display bytes may remain in RAM.

Save through stdin to ciphertext staging. Verify as required, recheck original revision and cancellation, then atomically replace. Keep failed drafts. Private metadata selection and previews use provider entries and virtual paths; refresh after Pull. Successful metadata saves invalidate previews. `test_local_crypt_lifetime*.py` covers revocation and abandoned opens.

## Filename discovery and batch mapping

`note_lookup.py` prunes hidden or inadmissible entries and batches encrypted basename lookup without reading note bodies or persisting decoded names. `path_batches.py` deduplicates and preserves order, caps requests by bytes and count (CLI 128, native 256), and verifies access before/after each batch. Native `encode: true` is additive; omitted means decode. Rebuild the bridge for batched encoding.

## Mobile storage and provider ownership

`localcrypt/mobile/copies.py` reads existing UUID copies; reviewed folder pulls use mappings in `transfers/mobile/jobs.py`. Bind encrypted paths to the crypt fingerprint independently of OAuth changes. Keep decoded names and keys out of records. Import/restore validate the allowlisted backing remote in the same package. Mobile does not import desktop ciphertext-copy directories.

`CryptContentProvider` serves managed and downloaded copies. `archive_source.py:NativeSource` binds generation and ciphertext revision; `crypt_stat/range/archive` operate on caller-owned ciphertext descriptors. Retire archive tokens and reject late cache publication. `crypt_decode` remains bounded legacy support. No plaintext archive file is created. [Reader access trace](../../../development/architecture/document-storage.md#trace-a-mobile-provider-reader)

## Mobile verified saves and moves

`crypt_encode` writes to an empty independent descriptor. Verify staged plaintext and check original revision before atomic replacement. Mobile text and Markdown edits cap at 1 MiB. Carry encoding, BOM and endings through `TextSnapshot`; preserve failed drafts and resolve dirty edits before credential changes. Moves stream rewrapped ciphertext, retire the progress watcher before closing the descriptor and verify before removing source. Use the `workspace-move` native probe.

`services/documents/metadata.py` owns shared manifests. Native `crypt_metadata` authenticates the inner archive, rewrites only metadata and preserves untouched raw members. Verify manifests and reparse before publication. Rewritten protected metadata uses AES-256 with the original inner password. Inner passwords stay per-open in session memory.

## Push preflight

`transfers/push_policy.py` and native `MirrorJobs` refuse missing mappings, mismatched identities, changed ciphertext and unsafe storage. Desktop explicit incomplete approval skips full authentication and generated-file cleanup while keeping structural checks. Normal and mobile reviews retain full preflight. [Transfer workflow](transfers.md)
