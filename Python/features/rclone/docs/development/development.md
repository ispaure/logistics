# rclone Feature

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

rclone owns credential loading, remote folder sources and explicit-config push/pull.
`transfer_options.py` owns portable option validation and CLI/embedded option
encoding. Desktop and mobile both consume it; importing portable modules does not
initialize either UI, desktop configuration or credential state.
`review.py` owns the shared memory-only review state, partial/completed results,
comparison cancellation and stale-review comparison. `review_cli.py` is the
desktop read-only rclone adapter; `ui/review.py` presents it, and `workflow.py`
keeps approved execution routed through the existing mandatory sync preflight.
Mobile uses the same review state with `mobile/transfer_review_ui.py`
and the embedded `mirror_review` adapter. Programmatic synchronization APIs retain
their explicit low-level execution behavior; user-facing Push/Pull always reviews.
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

Loading uses `zipUtils.unzip_file` and shared ZIP access with an explicit credential
password, supporting plain, ZipCrypto and AES packages. Each load has an isolated
temporary workspace cleaned on success/failure. Failed extraction must not publish
a generated config. Comics' ancestor INI passwords and unlock caches do not apply.

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

Portable `scope.py` owns folder-name inference; `local_policy.py` owns ciphertext
inventory, generated-file cleanup classification and local file-link policy.
Mobile captures `TransferOptions` once for native review and execution; its
settings storage stays in the app container. CLI/embedded runners and crypt I/O
remain platform adapters. Mobile rclone controllers and providers now live in
`mobile/`; generic provider document hosting remains in `logisticsmobile`.

`local_crypt.py` owns ciphertext mappings, explicit backing-target routing, private
reader providers and verified encrypted replacements. `ui/local_crypt.py` owns
unlock prompts and private document presentation. See the [LocalCrypt architecture](localcrypt.md)
for ownership, cancellation, provider lifetime, desktop/mobile differences and
validation. Generic resource contracts are documented in commonUtils.


## Mobile ownership

`mobile/__init__.py` has no initialization side effects. Mobile-specific adapters
live under this feature; portable policy remains at the feature root.

| Owner | Modules / responsibility |
| --- | --- |
| Feature bridge and credentials | `mobile/cloud.py`, `credential_vault.py`, `credential_packages.py` |
| Feature transfer operations | `mobile/mirror_jobs.py` |
| Feature ciphertext storage | `mobile/localcrypt.py`, `file_resources.py`, `crypt_stream.py`, `previews.py` |
| Feature native presentation | `mobile/cloud_ui.py`, `mirror_ui.py`, `transfer_review_ui.py`, `localcrypt_ui.py`, `messages.py` |
| Generic app document hosting | `logisticsmobile/provider_ui.py`, `provider_readers.py`, `text_resources.py`, `native_archives.py`, `private_sessions.py` |
| Generic app integration | Folder Hub, Files, navigation/scenes, document persistence, screen privacy and OS picker access stay in `logisticsmobile` |

Feature UI adapters consume host navigation, pickers and document services through
explicit imports and the existing app/controller interfaces. Ciphertext storage
adapts to the app's generic memory-only reader; book/comic behavior is still owned
by those format features. Ordinary text resources and native archive facades do
not import rclone adapters. Host code imports feature services where it offers a
remote/encrypted capability. Removed `logisticsmobile` feature paths have no
forwarding modules; all in-repository callers and tests use their current owner.

`Mobile/tools.py` explicitly packages these modules and checks imports in both
host and feature adapters. Desktop-only rclone UI/configuration is excluded from
the mobile payload. `Mobile/rclone_bridge` stays alongside native build tooling:
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

`mobile/file_resources.py` contributes encrypted collection roots and reader
stores to generic library/navigation hosts. `mobile/mirror_jobs.py` resolves
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
thumbnail requests. `logisticsmobile/browser_preview.py` retains generic preview
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
