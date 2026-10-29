# Credential loading and lifetime

## Credential contract

Desktop package discovery selects Marc's existing Dropbox
`Software/GIT/logistics/Credentials/rclone` folder when available, otherwise the
configured local credential folder. It never combines the two lists. Imports
and the displayed import folder use that same selection. Config and session keys
retain their existing ZIP-basename identity.

Desktop Settings discovers credential packages with a cancellable
`OperationProgress` worker, including optional-root selection and recursive
scanning. It retains the previous rows, selection and password until a successful
scan is ready. Scan failures and cancellation keep the previous list available
for retry. Row replacement blocks selection signals only within a scoped guard;
closing during discovery requests cancellation and waits for worker retirement.
Imports refresh through the same worker and select the imported ZIP on success.
`test_credential_import_ui` covers failed refresh, retry, event-loop responsiveness
and rejection of cancelled late results.

With **Persistent — save on this device** selected, unlocking `Credentials/rclone/Personal.zip`
creates `~/.config/rclone/Personal.conf` without changing the ZIP. With **Session only** selected,
credentials remain in a process-local session identified by a virtual `.session`
path; no plaintext config or extracted TXT is written. Forgetting or replacing a
parent session also revokes private LocalCrypt reader sessions. Entries are `.txt` files starting with a rclone section
header such as `[Media]`, followed by configuration lines. Forgetting a selected
package removes its saved config, session credentials and remembered names; Clear All removes every
directly contained `.conf`, including a legacy `rclone.conf`. Both preserve the ZIP.

All `.conf` files in that directory are sources, including configs without a
corresponding ZIP. Initialization only creates the config directory; it never
merges credentials into a global config. The checkout's credentials directory
may be empty, and Logistics Local folders work without this feature.

Desktop Settings submits `DesktopCredentialLoad` through the shared
`RcloneService.credentials`. An `OperationProgress` worker prepares the ZIP using
`session.read_package`. The desktop adapter validates password-protected TXT
entries in memory and atomically writes the config for **Load on Disk**;
**Load for Session** publishes values on the GUI thread. It never extracts TXT files or starts rclone. Cancellation
before publication preserves existing credentials; once the disk write commits,
cancellation does not remove the saved file. Closing Settings requests cancellation and defers
closure until the worker stops. Completion updates the selected row without
rescanning cloud-backed credential roots. The legacy programmatic
`load_remote_from_zip_to_config` helper now uses the same service and in-memory
validation for disk and session loads. The unused extracted-TXT loading/writing
helpers were removed. Comics' ancestor INI passwords and unlock caches do not apply.


`CredentialService.prepare_load(request, password, context)` returns a one-use,
service-owned `PreparedCredentials` admission without publishing credentials or
saved files. `unlock(prepared)` publishes that staged load; `load(...)` combines
both steps when the platform can run them on one worker. Passwords are separate
arguments and never appear in requests, admissions or results. Discarding or
collecting an admission releases staging; consumed or foreign admissions cannot
publish. The desktop adapter copies settings into the session before clearing
its staging dictionaries. LocalCrypt backing/password checks happen before
publication, so invalid crypt settings preserve the old session.
Desktop preparation captures the bounded ZIP digest and file revision before
decoding. Publication rejects a replaced package and uses the captured digest for
the reader-state key, rather than rereading a different archive at publication.

The service guards publication with nonblocking admission. A lock, a forget, an unlock
publication attempt, or saved-vault restore retires other pending loads in that
service; the platform generation/file checks also reject stale loads. Pending
loads have named stage, context, epoch and cleanup fields; one invalidation method
advances the epoch and retires staging for every publication/revocation path.
Admissions are conservatively invalidated across packages within a service,
while existing desktop access grants retain their package-specific revocation.
Cancellation and host validity are checked before publication, including the
atomic saved-file commit. A completed publication remains committed if a caller
cancels afterward; cancellation does not roll credentials back. Notification
failures after publication can likewise leave the new credentials active.

Desktop Workspaces and the standalone unlock prompt prepare on a worker and
publish on the GUI thread through this same authority. `DesktopCredentials` in
`desktop_credentials.py` owns publication; `desktop_service.py` only composes it.
The native equivalent is `mobile/credentials.py`, with `mobile/service.py` limited
to wiring. A native prepared stage is wrapped without mutating the stage supplied
by the loading adapter.
Native `mobile/credential_loading.py` captures a bounded ZIP and alias snapshot,
then delegates atomic import, device-vault restore, or SMB addition to the
existing `CloudClient`/native authorities. Native ZIP passwords remain necessary
for retained session ZIPs; this does not turn device retention into an unlock.
`credentials.retain(NativeCredentialRetention(...))` resolves connection identities
and package aliases through the native adapter, then asks `CredentialPackages` to
retain only the original password-protected ZIP. Its request carries the selected
package, storage port, remote names and loaded generation; stale generations or
foreign stores are refused. Native load results carry the generation captured
under the publication lock, so retention cannot silently adopt a later load.
Folder-type metadata repairs use the same entry point
with `NativeCredentialMetadata`, so they cannot recreate an index after forgetting. `run_credentials` guards host validity and cancellation
before retention starts. Once storage work starts it finishes before the worker
retires. Retention leaves loaded credentials and existing access grants unchanged;
failure is reported separately from successful credential loading. Saving decoded
credentials remains the `remember` choice on the original load request on both
platforms. UI hosts resolve private edits, pick documents and present prompts.

`credentials.forget(...)` serializes erasure with publication and retires staged
loads. Desktop accepts one `.conf`/`.session` path; omitting the path removes all
saved `.conf` files in the configured directory, preserving session-only packages.
The selected-package action forgets both its saved and session paths. Forgetting
revokes loaded access even if no saved file exists, removes the saved file even if
an in-memory session also exists, and preserves the source ZIP and local copies.
Legacy configuration deletion helpers delegate to this same service.

Native `NativeCredentialForget` supplies a lazy package-store resolver and the
credential document-cache root. The service clears live credentials and the saved
vault, retained ZIPs and encrypted document lists. The native publication lock
covers storage work across clients/scenes, including the vault clear/erase gap.
Independent cleanup continues after failures, which are reported as potentially
partial erasures. The package store's forget-only construction skips a damaged
index and enumerates owned encrypted blobs, including orphaned writes. It keeps
the index on failed cleanup for retry. Retained metadata updates and successful
erasure also update already-open package stores for the same root across scenes. Forgetting does not cancel halfway when a
view closes. Hosts clear presentation preferences and package labels after success;
read-only retained metadata discovery stays available without unlocking.

Mobile credential workers use `run_credentials`: cancellation keeps the host busy
until the worker retires and suppresses publication if it has not started yet.
Navigation/client/host checks prevent stale load results from resuming a different
view. `credentials.restore()` is the saved-vault entry point; `credentials.lock()`
continues to retain saved config/ZIP storage. Native locking still affects all
loaded packages together. The bridge remains the final busy/publication authority
across scenes and clients.

`test_credential_service.py`, `test_native_credential_service.py`,
`test_archive_credentials.py`, the Settings/Workspaces unlock tests and mobile
credential/retention/SMB suites cover these boundaries. The host native-bridge
fixture saves/restores and forgets a native vault and retained ZIP using synthetic
protected keys, loads credentials through the service, and runs the remote/transfer
slice, locks and reloads them, and verifies that old grants stay revoked.
These checks do not constitute physical-device validation.

Mobile imports, saved-vault restores and SMB credential additions use a nonblocking
native credential-publication scope. Active network operations or local readers
produce `credentials_busy` immediately, preserving credentials and the active
operation's cancellation handle; callers must retry after stopping that operation.
The Python scene-publication lock also refuses contention for these actions.
Credential metadata and package protection run outside the network queue.
Backend disconnects run after detachment in a background task. Global rclone cache
eviction, which can also disconnect backends, is deferred until the next explicit
online filesystem operation. Import itself never opens or validates an online
filesystem. Unlocking to resume a requested online action may subsequently run it.

## Desktop credential import and unlock presentation

`credentials.import_credential_package` reads a bounded (1 MiB) ZIP without
extracting it and atomically publishes a copy into the configured
`path_logistics_remote_cred` directory. It validates suffix/container, preserves
the original and rejects replacement of a different same-named package, including
publication races. Reimporting identical bytes is idempotent. Missing discovery
roots produce an empty list rather than preventing first-run import.

`ui.page.RclonePage` exposes Import and Refresh alongside the list. Import uses its
existing cancellable OperationProgress owner, selects the copied package and keeps
the user on the credential page. Unlock and password Return both open
`ui.credential_unlock.CredentialUnlockDialog`, whose parallel session/persistent
choices precede the existing credential service. Cancel performs no publication.
Existing saved-config presence is disclosed; session-only does not remove it.

Pull descriptions identify Cloud → Local or LocalCrypt. Initial session-crypt
storage selection explains encryption and retention, followed by the existing
mandatory transfer review. Pull contributions omit the redundant generic
destructive-action prompt; the review and captured execution/preflight remain.
`test_credential_import_ui.py` covers first-run discovery/import, selection,
collisions, invalid/cancelled imports, refresh, retry and retention UI;
`test_rclone_session.py` retains asynchronous publication/cancellation tests and
`test_rclone_pull_choice.py` covers storage routing and review admission.


## Remembered desktop session destinations

Successful session credential publication writes `<account>.session.json` beside
the user rclone configs. The bounded, versioned catalogue contains only schema,
absolute ZIP path and remote names; passwords, tokens, remote settings and decrypted
TXT/config bytes are excluded. `desktop_catalog` owns atomic publication, bounded
validation and deletion. Session lock retains this record; explicit session Forget
removes it. Failed/cancelled admissions do not create a record. Existing session-only
packages populate the catalogue on their next successful unlock.

Desktop source discovery merges remembered session destinations with active/saved
configs and existing copy associations. A saved `.conf` suppresses a duplicate
inactive session placeholder. Remembered names remain subject to existing remote
exclusions and the session-scoped Legacy visibility filter. Their `.session`
contexts and ZIP locations route into `WorkspaceUnlockView`; discovery itself
neither decodes the ZIP nor contacts the server. The existing admission, close,
revocation and late-result guards still own successful unlock and browsing.

Cloud's empty Files pane offers + rclone, opening personal rclone credential
settings and selecting the credential tab. Package paths and credential cleanup
are collapsed behind separate details/management controls on the loader.
`test_credential_catalog_desktop.py` verifies a fresh-process restart, persisted
field allowlist, failed/cancelled publication, Forget and saved-config deduplication.
`test_folder_sources_ui.py` covers the Cloud setup route, remembered locked names,
inline password routing and Legacy visibility. Host validation uses offscreen Qt.

## Mobile workflow and presentation

`mobile/credential_workflow.py` defines `CredentialPresentation` and
`CredentialLoadWorkflow`. The workflow runs the service load, captures its published
generation, refreshes remote kinds and checks that the client, navigation and
published generation still match before returning a result. It imports no toolkit.

`CredentialLoadPresentation` in `mobile/credentials_ui.py` adapts the host's current
binding, private-editor checkpoint, metadata refresh and loaded-package display.
The UI retains storage prompts, password fields, retained-ZIP selection and navigation.
Passwords are consumed before dispatch and cleared in the existing finally paths.
A cancelled worker retains ownership until `run_credentials` has retired it.

Credential failures log the fixed operation name, exception type and function/line
locations through `diagnostics.report_failure`. Exception text, payloads, locals and
credential values are excluded from those diagnostic records. Diagnostic sink
failures cannot replace the original credential error or prevent UI cleanup.

See [transfer handoff](transfers.md) for captured grants and
[LocalCrypt](localcrypt.md) for private reader lifetime.

A retained-package unlock reflects committed remote publication even if that
package cannot resume the requested folder connection. A mismatched package does
not resume the transfer or record a successful association for that request.
