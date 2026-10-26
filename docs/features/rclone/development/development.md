# rclone Feature

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

rclone owns credential loading, remote folder sources and explicit-config push/pull.
`transfers/transfer_options.py` owns portable option validation and CLI/embedded option
encoding. Desktop and mobile both consume it; importing portable modules does not
initialize either UI, desktop configuration or credential state.
`transfers/review.py` owns the shared memory-only review state, partial/completed results,
comparison cancellation and stale-review comparison. `transfers/review_cli.py` is the
desktop read-only rclone adapter; `transfers/ui/review.py` presents it, and `transfers/workflow.py`
keeps approved execution routed through the existing mandatory sync preflight.
Mobile uses the same review state with `transfers/mobile/review_ui.py`
and the embedded `mirror_review` adapter. Programmatic synchronization APIs retain
their explicit noninteractive behavior through captured service plans; user-facing
Push/Pull always reviews.
The mobile review entry initializes cloud controls without navigation before
credential checks, so mapped Workspaces Pull/Push also works on a cold launch.
`test_workspace_popup_menus.py` covers both cold command paths.
It has no hard feature dependencies; FUSE and Plex depend on it, while YouTube
Downloader uses it optionally. See the [user guide](../user/user.md) for controls,
[resource setup](../../../user/configuration.md) for paths/provisioning, and
[UI architecture](../../../development/features.md#remote-folder-source-context) for source wiring.

## Find the contract you need

| Change or question | Start here |
| --- | --- |
| Which module owns the change? | [Service ownership](#service-ownership) |
| Load, restore, lock or forget credentials | [Credential contract](#credential-contract) |
| Package labels, aliases and credential groups | [Credential presentation workflow](#credential-presentation-workflow) |
| Transfer approval and captured options | [Review and execution handoff](#review-session-and-execution-handoff) |
| Mobile writer admission, progress or native wire routing | [Native execution and wire boundaries](#native-execution-and-wire-boundaries) |
| Ciphertext paths, reader lifetime or verified saves | [LocalCrypt data flow](localcrypt.md) |
| Online provider access and cancellation | [Read-only remote browsing](remote-browsing.md) |
| Mobile capabilities and migration records | [Parity and migration reference](rclone-parity.md) |

The ownership table and contracts describe the current implementation. Dated
audit sections in the detailed guides retain the context and validation scope of
earlier changes; they do not establish validation of a new change.

## Service ownership

Composition modules wire adapters together; they do not publish credentials or
own navigation. Read these owners when changing a particular responsibility:

| Responsibility | Owner |
| --- | --- |
| Shared credential admissions, grants and service composition | `service.py`, `credential_loading.py` |
| Remembered desktop session remote names and ZIP locations | `desktop_catalog.py` |
| Desktop wiring / credential publication and revocation | `desktop_service.py` / `desktop_credentials.py` |
| Native wiring / process-wide credential adapter | `mobile/service.py` / `mobile/credentials.py` |
| Native ZIP/SMB preparation and cancellable workers | `mobile/credential_loading.py` |
| Native retained ZIPs and association metadata | `mobile/credential_retention.py`, `mobile/credential_packages.py` |
| Managed LocalCrypt and offline-copy references | `localcrypt/mobile/locations.py` |
| Desktop ciphertext copy identity, records and backing-target routing | `localcrypt/mapping.py` |
| Remote and LocalCrypt session lifetime / transport | `remote_resources.py`, `mobile/remote_resources.py`, `localcrypt/backend.py`, `localcrypt/mobile/resources.py` |
| Desktop private read-cache lifetime and budgets | `localcrypt/read_cache.py` |
| Session-bound desktop crypt command execution | `localcrypt/transport.py` |
| Native request progress lifetime / widget projection | `mobile/activity.py` / `CloudActivityPresentation` in `mobile/cloud_ui.py` |
| Shared transfer admission and execution lifetime | `transfers/service.py` |
| Platform transfer plans | `transfers/desktop.py`, `transfers/mobile/plan.py` |
| Native credential catalogue projection | `mobile/credential_catalog.py` |
| Native writer admission, execution state and progress | `transfers/mobile/execution.py` |
| Go wire admission / request routing / operation locks | `mobile_build/rclone_bridge/{protocol,requests,operation_scope}.go` |

Both compositions capture their credential adapter directly when constructing the
transfer service. Plans do not reach back through a partially constructed global
service or client attribute. Desktop and native transfer request construction uses
named fields for direction, options, mapping state and launch hooks.

### Follow an encrypted read or save

Desktop `CryptResources` owns virtual-to-physical validation and document policy.
It delegates credential-bound command execution to `CryptCommand`, and private
metadata/byte retention to `PrivateReadCache`. The command adapter receives one
session context and the provider's cancellation/access checks; it never writes
decoded configuration. The cache validates access under its retirement lock,
including hits and late worker publications. Closing retires all cached data
before notifying session observers. See the [LocalCrypt data flow](localcrypt.md#desktop).

For a save, follow `CryptResources.replace_stream`: stage ciphertext, read back and
verify, revalidate the original, publish, then clean staging. Cleanup forgets the
temporary logical path's encoded name, size and verification blocks together.
The provider retains file revision and mutation policy; neither the cache nor the
command adapter can authorize publication.

Mobile `CloudUI.remote_activity` delegates to the controller's `RemoteActivity`.
Its presentation port updates existing status controls and the progress bar; the
workflow owns the timer, nested request ordering and worker callback retirement.
Credential and transfer workers keep their own cancellation and publication rules.
The new module is declared in the feature's mobile manifest and portable-import
checks. `test_remote_activity`, `test_localcrypt_cache_retirement`,
`test_localcrypt_transport` and real-rclone `test_localcrypt_file_operations` cover
these boundaries; `python3 dev.py test-owner rclone` selects the feature suites.

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

## Folder identity and context

Contribute one remote source per loaded config. The Folders page groups them under
rclone and filters by credential; a refresh reads configs/folders once, and credential
changes reuse that snapshot. Match local folders to remotes by exact case-sensitive
name. Equal remote names from different credentials remain separate entries; preserve
the selected config path as opaque backend context through refresh and actions.

Credential labels do not change remote names: managed local folders use
`Local/<folder>`. FUSE uses `NetworkMount/<config-path-hash>/<remote>` to isolate
same-named remotes in different configs. Session Pull associates a local destination
with its package and blocks conflicting ownership. `storage.py` keeps LocalCrypt
and decrypted-copy connection records under the Logistics per-user application
support root, relocating legacy Server storage without replacing existing data.
Unloaded accounts are represented only by valid associations with existing copies;
loaded accounts also expose remote-only folders. Generic local-source
merging and selection restoration belong to the core folder services, not rclone UI.
Mounting belongs to the separate FUSE feature.

## Executable policy

Use `services.software.get_software('rclone')` for the pinned spec/path and
`ensure_software('rclone')` immediately before executing a command. Startup/source
discovery must not download software. A cancelled, declined or failed provision
returns no executable and must stop the command. Downloads do not make transfers
asynchronous.

The [software manifest](../../../../Python/software_manifest.json) supplies versions, HTTPS URLs,
archive/executable hashes and platform/architecture paths, with feature `config.ini`
overrides for rclone read by the software service.
Use its authoritative path rather than legacy binaries or a second download path.
See [updating pins](../../../user/configuration.md#public-software-provisioning) and
[shared provisioning recipes](https://github.com/ispaure/commonUtils/blob/main/runtime/streams/downloads.md#provision-a-pinned-executable-or-installer)
for reusable verification, staging and worker behavior.

## Validation

Use the [project test commands](../../../development/getting-started.md).
`test_archive_credentials.py` covers in-memory package validation/config output,
`test_folder_sources_ui.py` covers source selection/context, and `test_software.py`
covers provisioning policy. Tests use local fixtures and mocked providers; actual
remote transfers and credential ownership of existing mounts need platform checks.

## Structured progress monitor

GUI push/pull and explicit `rclone_sync()` calls use the shared QProcess runner,
argument vectors, and rclone's own retry policy. The JSON `stats` dictionary is
mapped to dedicated bytes, files, checks, speed, ETA, elapsed time and error fields;
reported active transfers update in place. Operation, source and destination have
separate labels. Missing statistics remain “Not reported”, and actual process exit
confirms success/failure. Cancellation clears live speed/ETA and active transfers
while retaining the last measured progress. Dry-run byte counts are labeled planned
work, because rclone includes simulated work in its statistics.

Raw JSON/console diagnostics remain under Details and logs. Non-stat log messages
retain the last progress values rather than resetting the monitor. Query/synchronous
console APIs retain their previous behavior. The installed pinned executable is
used by `test_rclone_structured_ui.py` for local copy/sync/move, dry-run/check, actual
failure and cancellation; cloud credentials and live remote contents are untouched.
The format follows [rclone JSON logging](https://rclone.org/docs/#use-json-log) and
[core/stats](https://rclone.org/rc/#core-stats-returns-stats-about-current-transfers).

Rclone download metadata is editable in this feature's `config.ini`, with
platform-section overrides read by `services.software`. Missing fields fall back
to the pinned root manifest; other tools still use that manifest. Both download
and installed hashes remain required. See
[configuration](../user/download-versions.md#rclone-download-versions).


## LocalCrypt

`remote_resources.py` supplies the desktop read-only remote provider. `ui/remote_browser.py` owns remote locations,
account selection and File Browser tabs; `remote_policy.py` defines portable
direct-open limits and the manual-copy message. Mobile's `mobile/remote_readers.py`
adapts native `remote_stat`, `remote_range` and `remote_archive` calls to the existing
private document hosts. These providers declare no remote mutation capabilities.
See [remote browsing](remote-browsing.md) for lifecycle,
identity, cancellation and validation boundaries.

Portable `transfers/scope.py` owns folder-name inference; `transfers/local_policy.py` owns ciphertext
inventory, generated-file cleanup classification and local file-link policy.
Mobile captures `TransferOptions` once for native review and execution; its
settings storage stays in the app container. CLI/embedded runners and crypt I/O
remain platform adapters. Mobile rclone controllers and providers now live in
`mobile/`; generic provider document hosting remains in `mobile`.

The cloud controller passes its application host to native credential-vault
creation, including retained ZIP storage. Android requires the real native
activity and application storage policy; workflow controllers do not supply them.

`localcrypt/mapping.py` owns ciphertext mappings and explicit backing-target routing.
`localcrypt/backend.py` owns private reader providers and verified encrypted replacements.
`localcrypt/ui/views.py` owns
unlock prompts and private document presentation. See the [LocalCrypt architecture](localcrypt.md)
for ownership, cancellation, provider lifetime, desktop/mobile differences and
validation. Generic resource contracts are documented in commonUtils.


## Mobile ownership

`mobile/__init__.py` has no initialization side effects. Mobile-specific adapters
live under this feature; portable policy lives in its owning workflow.

| Owner | Modules / responsibility |
| --- | --- |
| Feature bridge and credentials | `mobile/cloud.py`, `credential_vault.py`, `credential_packages.py` |
| Feature transfer operations | `transfers/mobile/jobs.py` |
| Feature ciphertext storage | `localcrypt/mobile/copies.py` catalog, `resources.py` providers, `content.py` content/write boundary, `archive_source.py` native ranges |
| Feature native presentation | `mobile/cloud_ui.py`, `mirror_ui.py`, `transfer_review_ui.py`, `localcrypt_ui.py`, `messages.py` |
| Generic app document hosting | `mobile/provider_ui.py`, `provider_opening.py`, `private_sessions.py`; `services/documents/provider_documents.py`, `mobile_storage.py`, `archive_access.py` |
| Ordinary mobile storage | `services/documents/locations.py`, `mobile/document_imports.py` |
| Generic app integration | Workspaces, Files, navigation/scenes, document persistence, screen privacy and OS picker access stay in `mobile` |

Feature UI adapters consume host navigation, pickers and document services through
explicit imports and the existing app/controller interfaces. Ciphertext storage
adapts to the app's generic memory-only reader; book/comic behavior is still owned
by those format features. Ordinary text resources and native archive facades do
not import rclone adapters. Host code imports feature services where it offers a
remote/encrypted capability. Removed `mobile` feature paths have no
forwarding modules; all in-repository callers and tests use their current owner.

`mobile_build/tools.py` explicitly packages these modules and checks imports in both
host and feature adapters. Desktop-only rclone UI/configuration is excluded from
the mobile payload. `mobile_build/rclone_bridge` stays alongside native build tooling:
it is the embedded Go/C-ABI target and also supplies ordinary archive/image I/O.
This ownership pass changes Python organization, not stored paths, schemas,
credential formats, bridge actions or transfer behavior.


Mobile managed-copy records now use schema 4 and store connection/destination
bindings without content-hash baselines. Schema-3 mappings load without moving
files; their unused baseline is omitted on the next record save. Schemas 1/2 and
old snapshot journals no longer run compatibility/recovery code; unsupported
records and old backup trees are preserved. Entry validation is metadata-only,
with ordinary file-link following and strict crypt link/hard-link rejection.
Crypt Push still streams every file through native authentication and checks
its file/tree versions before Sync. Directory names are checked against the
crypt mapping as well. The current review covers directory membership/type,
including decoded crypt folder names, without unstable directory timestamps.

`localcrypt/mobile/resources.py` contributes encrypted collection roots and reader
stores to generic library/navigation hosts. `transfers/mobile/jobs.py` resolves
managed local targets and decoded remote locations. Host code does not construct
crypt providers or reconstruct their physical layout for those routes.

Both native Sync and dry-run review use the operation-scoped CLI retry policy.
A new review attempt clears its changes and revisions. Native progress and final
results replace shared `ReviewScan` snapshots atomically; desktop JSON retry
boundaries also discard failed-attempt rows. Cancellation interrupts retry waits,
and completed-review approval still requires a fresh matching recheck.

The retired per-file mirror list/read/stat/mkdir/write endpoints and their byte
counter are removed. Native fixtures now seed and observe data through folder
Sync. `mirror_validate`, private descriptor checks, crypt authentication and
connection/destination binding remain production requirements. Generic remote
browsing, document reads and encrypted editing retain their own scoped APIs.

## Consolidation status and platform boundaries

The Python ownership move and final four audit items are implemented. Desktop
reviews now include directory rows, using membership/type rather than directory
timestamps for revisions. Crypt directory labels use a name-only synthetic final
file component so filename/directory encryption modes decode correctly; no probe
file is written. Desktop schema-1 hashed mappings are no longer loaded or
published. Unsupported records and old ciphertext stay untouched; a conflicting
unsupported record blocks a replacement mapping.

Desktop and native engines both pin rclone 1.74.1. Feature INI and fallback
manifest pins match, including verified ZIP and extracted-executable SHA-256
hashes for all six desktop platforms. A regression checks those pins against the
Go module and native build version. New versions still require platform testing.

`mobile/previews.py` owns native crypt preview source construction and encrypted
thumbnail requests. `mobile/browser_preview.py` retains generic preview
orchestration and format metadata, delegating encrypted I/O to the feature.
Existing controller callbacks remain host/feature integration points; this move
has not replaced them with a new host API. The [implementation record](rclone-parity.md#current-audit--2026-10-15)
separates completed consolidation from existing mobile capability limits.

Bounded non-streaming crypt fallbacks remain used by fallback clients and fixtures;
the normal native client uses streaming. `crypt_decode` also verifies staged text
saves in production and must not be removed as a fixture-only helper. These APIs
are separate from the removed per-file mirror transfer operations. Crypt Push
validation, link rejection, descriptor guards, identity and destination binding
remain mandatory after review, including explicit early approval.

## Mobile host boundary

The feature imports no `mobile` modules. `mobile/host.py:MobileHostUI` declares injected presentation callbacks. Transfer status uses its
`refresh_folder_source_actions` callback to refresh host toolbar visibility
without importing the application package. The application supplies browser/menu/picker and visibility policy through its composition root. Document reader and native archive adapters live in neutral Logistics services; rclone owns storage and transfer adapters.

## Workflow ownership

`transfers/` owns review, scope, options and execution policy, with desktop `ui/` and mobile presentation/controllers. `localcrypt/` owns encrypted providers/connections with desktop `ui/` and `mobile/` adapters. Cloud credential/session composition stays at the feature root/mobile package.

## Mobile source manifest

`../../mobile_sources.json` declares this feature's selected portable/mobile sources. Update it when adding an imported module. The build tool aggregates and checks the allowlists without starting desktop registration.

## Mobile connection ownership

`mobile/controller.py` owns `CloudState` (client and busy flags) and an explicit
`SMBFormState`. `mobile/smb_connection.py` owns SMB form construction, guest/account
presentation and asynchronous connection submission through `ConnectionHost`.
The form consumes and clears its password before dispatch. State stays on the
cloud controller; app-level field and method accessors remain compatible.
`test_connection_settings.py`, `test_smb_ui.py` and `test_workflow_ownership.py`
cover this boundary. Update the owner mobile manifest with source moves.

## Python–Go bridge contract

`mobile/bridge_protocol.py` owns supported Python action names and validates the
response envelope. `mobile_build/rclone_bridge/protocol_contract.json` is a public,
synthetic contract fixture consumed by Python and Go tests. It is not a native
payload or credential store. The contract is version one; no new wire version or
saved-data migration is introduced.

The ABI remains `LogisticsCloud(action_utf8, request_json_utf8)` followed by exactly
one `LogisticsCloudFree(pointer)` for each non-null response. Requests are objects;
replies have boolean `ok`, optional `result` and optional `error`/`error_code`
fields. Cancellation acknowledgements need no result; probe errors can omit text. Credential
publication may also return `credential_state`. `credentials_busy` refuses
publication immediately; `archive_password` requests an inner archive password.
Python checks the existing 2 MiB request limit (24 MiB for image thumbnails).
The Go mirror-review path separately permits larger review plans; Python's current
request bound remains unchanged.

Cancellation and progress retain the operation scopes in `operation_scope.go`;
credential replacement is serialized across scenes and invalidates their caches.
Contract fixtures cover action-name parity and safe cancellation/status/error
responses. Operation-scope and credential-loading tests cover the stateful cases.
Never capture real request payloads or credential responses as fixtures.

## Offline-copy workflow

`mobile/downloads.py` owns offline-copy selection, import routing, export and its
`DownloadState`. The cloud controller delegates existing callbacks to a composed
`DownloadWorkflow`; application compatibility fields still resolve to that same
state. Local copy opening retains navigation-generation checks, independent read
access during cloud work, provider-folder recording and the existing PDF/EPUB/text
routing. It does not own credential loading or create a second document store.

## Credential presentation workflow

`mobile/credentials_ui.py` owns credential package selection, retained associations,
unlock prompts and startup restoration. The cloud controller composes one
`CredentialWorkflow` and `CredentialState`; native credential publication and
cross-scene identity live in the process-wide `NativeCredentialState` composed by
`CloudClient` and the Go bridge. The state owns package identity resolution, resume
gates, publication epochs, observers and the publication lock; it imports no native
transport or widgets. Every client and scene uses the same state instance. Existing CloudUI
callbacks delegate to the retained workflow directly; focused tests construct that
owner rather than relying on a UI fallback to create it. Import `SelectedCredentialZIP`
from `mobile.credentials_ui`. A bounded
picked ZIP still consumes picker access immediately and retains only memory bytes.
Credential restoration, package, import, background-refresh and workflow tests
cover this extraction. Cloud browsing, busy policy and cancellation remain cloud
controller responsibilities.

`mobile/credential_catalog.py` snapshots nonsecret package names, aliases and remote
lists before computing labels, exclusions and credential groups. It preserves the
full package identity when basenames collide. Preference projection keeps session
associations in memory and bounds saved associations independently. It performs no
storage, toolkit or bridge operations. Credential publication and retention remain
service responsibilities. The UI workflow rechecks host, client, navigation and
the published generation after asynchronous metadata and identity work; a newer
credential generation cannot receive the older result's controls or preferences.

## Native execution and wire boundaries

`transfers/mobile/execution.py` owns `TransferState`, writer admission, coalesced
progress delivery and worker retirement. Progress renders the latest snapshot,
then leaves at least one second before another render, including when updates
arrive during slow native layout. Native polling and cancellation keep their
existing cadence; terminal outcomes publish immediately after worker retirement.
The presentation skips unchanged text, banner values and source-action spacing
to avoid repeated native layout work. `TransferController` exposes its existing
app fields through that state; `TransferExecutionPresentation` projects state into
controls. A second caller which also awaited credential restoration must pass a
fresh busy check before starting a writer. Cancellation retains busy ownership
until native work retires. Result validation must finish before marking completion;
malformed results and changed credentials remain terminal failures. Progress
messages and known-work percentages are computed without widget access.

`mobile/storage_location.py` captures each collection copy as one source, target
and inventory record. Conflict checks, free-space calculation, staging and final
verification consume those records, keeping their identities together through
pointer publication. The existing backup/adoption and verified-copy policy remains.

The Go bridge separates wire decoding, operation admission and response publication
in `protocol.go` from the domain dispatch in `requests.go`. `main.go` retains the C
entry points and engine helpers; `operation_scope.go` retains reader, transfer and
credential locking. The shared protocol fixture checks actions across both routing
owners and exercises actual dispatch. Run the Go suite with `go test -race ./...`
from `mobile_build/rclone_bridge` using the configured Go toolchain. A host
`-buildmode=c-shared` library supplied through `LOGISTICS_MOBILE_BRIDGE` also enables
the Python native LocalCrypt, folder-listing and file-operation integration checks.
These synthetic host checks do not establish physical-device UI behavior.

## Review session and execution handoff

`transfers.review.ReviewSession` owns approval state for both desktop and mobile.
Its immutable `ReviewRequest` captures direction, source, destination, connection
binding and transfer options; hosts provide a `valid` predicate for that binding.
A `ReviewScan` owns the comparison worker, cancellation and retirement. All of
this state is memory-only; approval is not a stored authorization for later runs.

After the platform's explicit confirmation, normal approval captures the complete
snapshot and starts a fresh comparison. Execution is approved only if both
fingerprint and change list still match and the binding remains valid. Changes
return the session to review. Explicit incomplete approval is a separate decision:
it stops the comparison and still waits for worker retirement before execution.
A cancelled scan immediately rejects either approval path, even before polling.
Invalidating credentials/bindings cancels the session; obsolete dialogs cannot
start a transfer against a new source.

UI adapters render snapshots and poll state; they do not duplicate this approval
machine. Desktop sync and mobile jobs retain mandatory execution preflight and
mutation/collision policy. A completed comparison is not an atomic storage lock
or a guarantee against later remote changes. Focused coverage includes
`test_review_session`, `test_rclone_review`, push-policy and mobile review tests.

Mobile retires the review route and its native controller when comparison closes,
before showing execution details. Back cannot reopen a consumed Push/Pull review,
including when comparison closes while another tab is visible. Reselecting the
Workspaces tab cancels an open comparison and returns to its root.

## Desktop provider lifetimes

`RemoteResources` and LocalCrypt `CryptResources` compose the shared
`ResourceLeases` and `WorkerCancellation` classes. Each provider retains its own
credential validation, explicit close, encrypted-path guards and cache cleanup.
Browser/document owners acquire independent idempotent releases; the last release
closes the provider. Nested worker cancellation restores the outer scope even on
failure, without affecting readers in another thread. LocalCrypt captures the
current predicate before invoking command, encoding and staged-save work.

Focused validation covers concurrent/duplicate releases, rejected acquisition,
nested scopes, exception restoration and thread isolation in commonUtils, plus
real rclone LocalCrypt reading, encrypted saves, cancellation, revocation and
remote browser workflows in Logistics.

`credential_sessions.CredentialSessions` owns desktop credential generations,
parent/child revocation, private-reader visibility, package associations and
process-private rclone environments. `session.registry` is the one application
instance; the existing module operations bind to that instance. ZIP decoding stays
in `session.read_package`, separate from lifetime state. Independent registries
can be created without touching the application's credentials. No credentials or
package contents are written by the registry.

Credential observers are all notified even when an earlier callback fails; the
first exception is re-raised after invalidation completes. LocalCrypt clears its
plaintext and path caches in a `finally` block on close. Registry parent cycles
are rejected before replacing an existing generation. Bridge busy errors may
omit optional error text and still raise `CredentialBusyError`. Synthetic failure
tests cover these paths without storing real credentials.

LocalCrypt cache publication and retirement share the provider's cache lock. Late
encoding, listing and recursive-search workers revalidate before storing decrypted
names; size/block hits and publications also revalidate under that lock. Closing
a provider atomically marks it closed and discards cached bytes, names and sizes
before notifying other revocation observers. The session notification runs after
releasing the cache lock. Paused-worker regressions cover closure between path
validation and publication, and observers verify that private caches are already
empty when they run.

## Application service boundaries

Desktop Open/Save pickers and Notes Library factories open LocalCrypt through
`RcloneService.localcrypt`. Mobile Notes Library mappings and restored private
documents do the same; restored remote documents open a remote session through
`RcloneService.remotes` and obtain its reader adapter. Browser preview readers use
the browser's captured remote resource, including its original generation.
The direct document API can open a fresh service session when no browser exists.
An identity mismatch during restored LocalCrypt setup closes the new provider.

Platform adapters still perform engine I/O and construct internal crypt comparison
and authentication providers. Metadata discovery (connection/cipher identities,
copy associations and crypt types), storage layout, document formats and browser
navigation remain with their feature owners; these are not alternate credential
publication or transfer launch paths. `test_rclone_service_boundaries.py` checks
application factory/engine-import boundaries, while adapter and native-bridge
regressions exercise actual captured access and cancellation.

## Captured transfer plans

`transfers/service.py` supplies the shared `TransferService`. Its runtime adapter
turns a captured `DesktopTransferRequest` or `NativeTransferRequest` into a
`TransferPlan` containing the immutable `ReviewRequest`, comparison adapter,
approval binding, execution lifetime and execution adapter. Desktop
`transfers/desktop.py` owns plan assembly and crypt comparison resources;
`transfers/workflow.py` presents the review and routes programmatic sync requests. Native `transfers/mobile/plan.py`
owns the comparison transport, captured mapping and execution binding;
`transfers/mobile/review_ui.py` presents the review. `RcloneService.transfers` retains the
approval authority for its runtime. Browser/UI state and engine execution stay
with their existing owners.

`review(request)` resolves the platform plan and starts the shared review lifecycle.
`prepare(plan)` remains the lower-level admission API for explicit adapters. Both return a
`PreparedTransfer`. Presentation confirms that review; it cannot authorize a
transfer by returning a boolean. `execute(prepared, context)` admits the captured
executor once, passing the original options and operation-scoped cancellation and
progress. A plan from another service, a modified review, a changed connection,
an unretired comparison or a reused approval is refused before execution.
Execution failure or cancellation consumes approval; retry requires a new review.
Reviewed and programmatic execution share one execution-lifetime method, which
combines host cancellation and captured access before invoking the platform plan.

`run(request, context)` retains the existing explicitly noninteractive transfer
API for automation. It constructs the same platform plan, checks its binding and
runs mandatory preflight without starting a comparison or inventing review approval.
Desktop actions and YouTube configuration/season sync enter through
`transfers/workflow.py:sync_transfer`; their interactive `review=True` paths still
use review/execute and the existing confirmation. The engine-level `sync.rclone_sync`
is transport/preflight code for adapters and low-level tests, not the application
entry point.

Completed review still performs a fresh matching comparison. Explicit incomplete
approval still waits for the comparison worker to retire and retains mandatory
LocalCrypt authentication, link, destination and connection checks. The plan does
not make remote Sync atomic or add rollback to partially completed transfers.
Saved-config revision checks belong to the credential adapter. Remote providers
validate that same grant rather than maintaining a second file-stamp policy.
Desktop session validity captures a credential generation rather than comparing
credential values, so reloading identical values invalidates old plans. Saved-config
grants capture both a file revision and a process-wide lock generation. Locking a
saved package revokes its plans and remote views without deleting the file;
reopening that file obtains new access and cannot revive an old grant. Lock All
also revokes captured saved-config grants. These checks apply during comparison,
launch hooks and running transfers, including noninteractive transfers.
The service checks request validity before starting comparison. Approval validity
includes the original copy records and mapping signature. Execution lifetime is
separate: saving those records during a valid transfer must not cancel its own
operation. The service combines the caller's cancellation with the captured
credential and host lifetime before invoking the adapter and throughout its
preflight and transfer work. Native admission also binds the collection target;
a relocated target cannot receive the approved transfer. Mapping dictionaries and
desktop launch flags are copied into immutable request snapshots. Desktop
comparison consumes that effective request instead of forwarding its fields
individually. The native scanner accepts direction explicitly; transient review
flags are not added to the persisted job's mapping shape.

Desktop rechecks access after its association-publication hook and before
preflight. Each crypt comparison owns its provider until the scanner retires.
Saved configs are read into a private credential snapshot for each comparison
and execution, with the original file revision rechecked before use. Rclone uses
that snapshot through its private environment and null config, so OAuth refreshes
cannot rewrite the saved file or invalidate their own approval. Comparisons
release snapshots when their workers retire. Synchronous execution releases its
snapshot on return; an accepted GUI process retains it until completion or window
destruction. An integrated process window retains a GUI-thread access/cancellation
monitor until the process completes, including saved-config transfers. A GUI launch still
returns acceptance rather than the process's eventual success; its progress
window owns that result. Legacy detached-terminal calls do not gain a completion
handle from this service. Service execution with private credentials runs
synchronously when an integrated GUI window is unavailable.

Native execution still uses `MirrorJobs.execute_review` and its mandatory path,
record, link, LocalCrypt authentication and verification checks. Its progress
monitor interrupts a native transfer when execution cancellation becomes active.
Cancelling the UI coroutine signals cancellation and keeps the transfer busy
until its worker retires, consuming late results and failures. Cancelling plan
preparation also waits for its worker and any late comparison to retire before
releasing the host, so late native cancellation cannot target the next transfer.

`test_transfer_service.py`, `test_transfer_adapters.py`, `test_rclone_review.py`,
`test_rclone_revocation.py`, mobile `test_native_transfer_service.py` and
`test_mirror_ui.py` cover the handoff alongside the existing engine/preflight
suites. `test_remote_bridge_native.py` additionally exercises reviewed native
ordinary and crypt Pull/Push against an in-memory remote. These are host tests,
not physical-device validation.

## Shared remote access

`RcloneService.remotes.open(location)` is the entry point for remote browsing and
Notes Library access on desktop and mobile. `remote_access.py` defines the session
contract and immutable platform references: desktop supplies a config path and
remote name; native supplies a remote alias, with optional expected connection
identity and credential generation. The service owns access construction; each
browser owns its navigation and each document owns its reader lifetime.

Desktop `remote_resources.py` retains explicit CLI configuration, range limits and
read-only capabilities. Each provider has a private child credential session and
captures its generation. Reloading identical settings revokes existing views.
Saved config views also verify device, inode, size, modification and change times
before returning results; locking retires views without deleting saved config
bytes. Explicit reopening can create new access from those saved settings.

Native `mobile/remote_resources.py` binds a session to its connection identity and
credential generation. `access.py` shares cancellation, leases and closure with
LocalCrypt providers. Listing and file reads validate access before and after
native requests. `RemoteReaders` retains the original grant and opens independent
sessions for documents; closing the browser or another document leaves them
usable. Locking or replacing credentials revokes every old session, including
reader stores that have not opened a document yet. Reopening a closed view never
rebinds it to a newer generation.

`mobile/browser_workflow.py` publishes a provider together with the listing.
Failed publication restores the previous rows, location and provider. Cancelled
listing workers retire late sessions without publishing them. Mobile remote
search filters the loaded listing and does not recursively enumerate the remote
or build a local search index. Preview-only controls and existing archive/range
limits remain in place. Archive cleanup retires the native cache token after a
failed or late download, even if the reader closed before cache publication.

Validation includes real CLI local/crypt backend fixtures in
`test_remote_browser.py`, the native bridge fixture in
`test_remote_bridge_native.py`, and mobile `test_remote_service.py`,
`test_cloud_browser_workflow.py`, `test_remote_readers.py` and Notes Library tests.
These host tests exercise the shared mobile workflow; they do not constitute a
physical Android or iOS device run.


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
