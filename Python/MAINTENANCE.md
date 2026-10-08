# Maintenance priorities

The generic application shell now has isolated regression coverage for feature
initialization, folder sources, page lifecycle, and action dispatch. The larger
remaining maintenance risks are in external integrations, where validation needs
representative fixtures and platform checks before behavior changes.

## Integration workflows

- **Plex:** read-only database access, episode/GUID comparison and staged package/
  restore handling now have fixture coverage. Validate Windows registry/7-Zip,
  stopped-server restore, large packages, Linux ownership and failure during
  multi-file archive promotion on real installations. Recovery copies intentionally
  consume disk space until manually removed after checking the restored server.
  Source scan errors abort packaging; Unix ZIP restores preserve ordinary mode
  bits but do not change ownership. Duplicate hash matches can be reassigned.
- **Calibre:** export planning, metadata naming, execution and launching are now
  separated and covered with temporary fixtures. Validate device capacity,
  replacement/deletion failures and real desktop launches on supported platforms.
  Checksum comparison trades additional reads for detecting same-size changes.
- **YouTube downloads:** INI parsing, shell-free arguments, execution and remote
  sync are separated. Linux uses system FFmpeg. Mocked tests cover quoting,
  failures and batch status. Keep package-updating policy separate from downloads;
  consider explicit updates and declared dependencies rather than automatic pip.
  Move long-running update/download/package operations into cancellable workers.
- **FUSE:** command construction, timeout handling, recovery and conservative
  cleanup now have simulated-state coverage. Actual mounting still requires
  macOS, Windows and Linux driver validation. Windows stale-mount recovery and
  verifying which credential owns an already-mounted same-named remote remain
  separate follow-ups; filesystem locations are shared across credentials.
- **Media renaming:** add plan-validation fixtures for duplicate destinations and
  CSV titles containing path separators before extending the rename workflow.

## Folder discovery and presentation

`LogisticsConfig` creates independent resource directories at the checkout root.
Optional `[Resources] software_path` and `credentials_path` entries in
`configFile.ini` override them independently (relative to the checkout, or absolute).
Dropbox is never selected implicitly. Public binaries/installers are pinned in
`software_manifest.json`; `services.software` supplies project policy to the shared
`commonUtils.downloads` and `commonUtils.ui.download` provisioning code. Download
hashes and extracted executable hashes must both be updated when changing releases.
Other integrations still require their existing private software resources.

Source listings are read once per page refresh, but refresh and folder feature
detectors still run on the GUI thread. If a large or unavailable source causes
visible delays, move discovery into a worker with cancellation and stale-result
handling. Preserve backend-owned credential context and selections when doing so.

The folder merge service identifies managed local folders by name. Dedicated
local sources can show same-named paths separately, but expanding managed local
discovery to several roots would require an explicit identity policy and tests.

## Validation boundaries

Run `python -m unittest discover -s Python/tests -v` with `PYTHONPATH=Python` from
the repository root using the project's virtual environment. These tests use
temporary files and mocked providers; passing them does not validate real remote
transfers, library exports, mounts, or desktop integration on every platform.
Keep shared-utility changes in their own repository and validate dependent
projects before updating the submodule reference.

## Platform checks

Plex comparison no longer embeds personal macOS paths; Linux package actions are
available alongside Windows/macOS. Downloader FFmpeg detection supports Linux.
Bedrock server discovery recognizes the Linux `bedrock_server` executable and
requires execute permission. These changes have mocked/fixture coverage; they
are not substitutes for native desktop and service testing.

Calibre's BOOX mirror still targets `/Volumes/BOOX-SD`, an explicit device workflow.
Generalizing its device selection should be a separate UI change rather than
assuming a removable-drive path on Windows or Linux. System repair and macOS power
settings are intentionally tied to their operating systems.
