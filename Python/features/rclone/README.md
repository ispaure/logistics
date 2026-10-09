# rclone Feature

rclone owns credential loading, remote folder sources and explicit-config push/pull.
It has no hard feature dependencies; FUSE and Plex depend on it, while YouTube
Downloader uses it optionally. See the [user guide](user_docs/index.md) for controls,
[resource setup](../../../CONFIGURATION.md) for paths/provisioning, and
[UI architecture](../UI_ARCHITECTURE.md#remote-folder-source-context) for source wiring.

## Credential contract

Loading `RemoteCredentials/Personal.zip` creates `~/.config/rclone/Personal.conf`
without changing the ZIP. Entries are `.txt` files starting with a rclone section
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

Credential labels must not change remote names or paths: managed local folders use
`Local/<folder>` and FUSE uses `NetworkMount/<remote>`, with no credential component.
Mount paths are consequently shared across same-named remotes. Generic local-source
merging and selection restoration belong to the core folder services, not rclone UI.
Mounting belongs to the separate FUSE feature.

## Executable policy

Use `services.software.get_software('rclone')` for the pinned spec/path and
`ensure_software('rclone')` immediately before executing a command. Startup/source
discovery must not download software. A cancelled, declined or failed provision
returns no executable and must stop the command. Downloads do not make transfers
asynchronous.

The [software manifest](../../software_manifest.json) is the sole source for
versions, HTTPS URLs, archive/executable hashes and platform/architecture paths.
Use its authoritative path rather than legacy binaries or a second download path.
See [updating pins](../../../CONFIGURATION.md#public-software-provisioning) and
[shared provisioning recipes](../../commonUtils/RECIPES.md#provision-a-pinned-executable-or-installer)
for reusable verification, staging and worker behavior.

## Validation

Use the [project test commands](../../../README.md#development).
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
