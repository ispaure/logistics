# rclone Feature

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

rclone owns credential loading, remote folder sources and explicit-config push/pull.
`transfers/transfer_options.py` owns portable option validation and CLI/embedded option
encoding. Desktop and mobile both consume it; importing portable modules does not
initialize either UI, desktop configuration or credential state.
`transfers/review.py` owns the shared memory-only review state, partial/completed results,
comparison cancellation and stale-review comparison. `transfers/review_cli.py` is the
desktop read-only rclone adapter; `ui/review.py` presents it, and `transfers/workflow.py`
keeps approved execution routed through the existing mandatory sync preflight.
Mobile uses the same review state with `transfers/mobile/review_ui.py`
and the embedded `mirror_review` adapter. Programmatic synchronization APIs retain
their explicit low-level execution behavior; user-facing Push/Pull always reviews.
The mobile review entry initializes cloud controls without navigation before
credential checks, so mapped Workspaces Pull/Push also works on a cold launch.
`test_workspace_popup_menus.py` covers both cold command paths.
It has no hard feature dependencies; FUSE and Plex depend on it, while YouTube
Downloader uses it optionally. See the [user guide](../user/user.md) for controls,
[resource setup](../../../../../docs/user/configuration.md) for paths/provisioning, and
[UI architecture](../../../../../docs/development/features.md#remote-folder-source-context) for source wiring.

## Credential contract

With **Save credentials locally** enabled, loading `Credentials/rclone/Personal.zip`
creates `~/.config/rclone/Personal.conf` without changing the ZIP. With it disabled,
credentials remain in a process-local session identified by a virtual `.session`
path; no plaintext config or extracted TXT is written. Forgetting or replacing a
parent session also revokes private LocalCrypt reader sessions. Entries are `.txt` files starting with a rclone section
header such as `[Media]`, followed by configuration lines. Removing a loaded
credential deletes only its `.conf`; Clear All deletes every directly contained
`.conf`, including a legacy `rclone.conf`, never credential packages.

All `.conf` files in that directory are sources, including configs without a
corresponding ZIP. Initialization only creates the config directory; it never
merges credentials into a global config. The checkout's credentials directory
may be empty, and Logistics Local folders work without this feature.

Desktop Settings decodes credential ZIPs in an `OperationProgress` worker using
`session.read_package`. It validates password-protected TXT entries in memory and
atomically writes the config for **Load on Disk**; **Load for Session** publishes
values on the GUI thread. It never extracts TXT files or starts rclone. Cancellation
before publication preserves existing credentials; once the disk write commits,
completion reports success. Closing Settings requests cancellation and defers
closure until the worker stops. Completion updates the selected row without
rescanning cloud-backed credential roots. The legacy programmatic
`load_remote_from_zip_to_config` helper still uses a private extraction workspace
for disk loads. Comics' ancestor INI passwords and unlock caches do not apply.

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

The [software manifest](../../../../software_manifest.json) supplies versions, HTTPS URLs,
archive/executable hashes and platform/architecture paths, with feature `config.ini`
overrides for rclone read by the software service.
Use its authoritative path rather than legacy binaries or a second download path.
See [updating pins](../../../../../docs/user/configuration.md#public-software-provisioning) and
[shared provisioning recipes](https://github.com/ispaure/commonUtils/blob/main/runtime/streams/downloads.md#provision-a-pinned-executable-or-installer)
for reusable verification, staging and worker behavior.

## Validation

Use the [project test commands](../../../../../docs/development/getting-started.md).
`test_archive_credentials.py` covers package extraction/config output,
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

`localcrypt/backend.py` owns ciphertext mappings, explicit backing-target routing, private
reader providers and verified encrypted replacements. `localcrypt/ui/views.py` owns
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
| Feature ciphertext storage | `localcrypt/mobile/copies.py`, `file_resources.py`, `crypt_stream.py`, `previews.py` |
| Feature native presentation | `mobile/cloud_ui.py`, `mirror_ui.py`, `transfer_review_ui.py`, `localcrypt_ui.py`, `messages.py` |
| Generic app document hosting | `mobile/provider_ui.py`, `provider_readers.py`, `text_resources.py`, `native_archives.py`, `private_sessions.py` |
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
cross-scene identity remain in `CloudClient` and the Go bridge. Existing CloudUI
callbacks and the `SelectedCredentialZIP` import remain compatible. A bounded
picked ZIP still consumes picker access immediately and retains only memory bytes.
Credential restoration, package, import, background-refresh and workflow tests
cover this extraction. Cloud browsing, busy policy and cancellation remain cloud
controller responsibilities.
