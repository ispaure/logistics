# Read-only remote browsing

Enter through **Workspaces → Cloud** or desktop **File Browser → File → Open Remote…**. See [Transfers](transfers.md) for Push/Pull and [LocalCrypt](localcrypt.md) for encrypted offline copies.

## Desktop browser and unlock

`RemoteBrowserView` clones `RemoteLocation` with account, remote and relative path intact. `ui/workspace_unlock.py:WorkspaceUnlockView` uses cancellable ZIP preparation and publishes only while active. Invalid passwords stay inline; source changes retire callbacks. Standalone uses its unlock dialog. Workspaces restores loaded/saved sources and remembered sessions; local copy associations alone create no Cloud placeholders.

Use isolated child credentials, process-private aliases and null config. Check saved revisions and live grants before/after I/O. Readers keep leases beyond tab closure; revocation retires existing readers. CLI failures expose sanitized recovery or exit status, with revocation taking precedence. Keep remote paths out of local mutations, indexes and external launchers.

**Download locally…** runs `transfers/remote_download.py` under the browser's
credential grant. It uses rclone `copyto` for files and `copy` for folders,
including empty directories. The worker stages beside the chosen destination
and publishes with an exclusive rename after checking cancellation and access.
The desktop Pull progress view shows rclone transfer statistics and reports
completion after publication.

## Mobile listings and connection admission

`mobile/browser_workflow.py` owns captured-location requests; `CloudBrowserPresentation` adapts controls. Restore a failed listing only for the same host, client and credential generation. `mobile/activity.py` owns status and rejects late callbacks. Online rows skip thumbnails; identity checks and native decoding run off the UI thread.

Loaded and retained packages supply Cloud rows. A matching copy scopes only its own account; stale mappings leave the loaded remote accessible while transfer identity checks still hold. Resolve aliases and published fingerprints before native probes. Test mixed saved/session credentials and duplicate remote names with `test_multi_credentials.py` and `test_folder_discovery.py`.

## Mobile reader opening and cache

`remote_readers.py:RemoteReaders` hands off an independent grant. `remote_source.py:RemoteSource` owns revision-bound ranges and remains re-exported by `remote_readers`. EPUB/ZIP uses `remote_cache_open` to fetch a validated RAM snapshot (128 MiB/file, 256 MiB/process); member reads use opaque tokens without further network I/O. Release on failure, close or revocation. Keep plaintext out of temporary files. [Reader lifecycle](../../../development/architecture/document-storage.md#trace-a-mobile-provider-reader)

Remote editors and metadata saves are read-only. Unsupported files offer a local copy. Archive password retry binds the item and generation and clears the field. [Selected mobile downloads](development.md#selected-remote-item-downloads-on-mobile)

## Mobile document history

Saved credentials need matching fingerprints for ordinary history. Protected session lists use AES-256 ZIPs keyed by the original ZIP password in native memory. Store references only, scoped by package and window. Clear on Forget and preserve malformed archives for recovery. Reopen online history with current loaded credentials, while offline copies still require matching identities.

## Native connection and archive errors

Go `main.go:clients` retains backend lifetimes, detaches cancellation hooks on normal completion and retires contexts on cancellation. `remoteRootFs` checks rooted identity, including colon-bearing paths. `crypt_stream.go:archiveContents` reports cancellation/deadline separately from inner passwords and sanitizes unencrypted member failures. Check `backend_lifetime_test.go`, `operation_scope_test.go` and `file_archive_test.go`.

## Remote reader validation

```sh
python3 dev.py test desktop --exact-file Python/tests/resources/test_remote_browser.py
python3 dev.py test mobile --exact-file mobile_build/tests/reading/test_remote_readers.py
```

Desktop synthetic CLI cases require pinned rclone. Mobile stubs cover recovery, bounds and revocation. Go `remote_document_test.go` covers native ranges, revision checks and cancellation; use `LOGISTICS_REMOTE_BRIDGE` with `test_remote_bridge_native.py` for a rebuilt host library.

## Offline folder snapshots

Validate drive/parent and entries at snapshot boundaries. LocalCrypt maps names in memory in batches of 256 under the local read scope. Reject stale host, request or credential generation before publishing native pages of up to 40 entries.

## Home credential unlock

`home_unlock_candidates` filters loaded and Legacy-hidden names using retained metadata. Home and Files unlock for the session, clearing passwords and resolving private edits. Home unlock returns to Home.
