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
  Downloads, explicit updates and season transfers now use cancellable workers.
- **FUSE:** command construction, timeout handling, recovery and conservative
  cleanup now have simulated-state coverage. Actual mounting still requires
  macOS, Windows and Linux driver validation. Windows stale-mount recovery and
  verifying which credential owns an already-mounted same-named remote remain
  separate follow-ups; filesystem locations are shared across credentials.
- **Media renaming:** CSV plans use the shared rollback-capable rename engine.
  Fixtures cover duplicate chapter numbers, invalid filenames and failed publication.

## Folder discovery and presentation

`LogisticsConfig` creates independent resource directories at the checkout root.
Optional `[Resources] software_path` and `credentials_path` entries in
`configFile.ini` override them independently (relative to the checkout, or absolute).
Dropbox is never selected implicitly. Public binaries/installers are pinned in
`software_manifest.json`; `services.software` supplies project policy to the shared
`commonUtils.runtime.streams.downloads` and `commonUtils.ui.download` provisioning code. Download
hashes and extracted executable hashes must both be updated when changing releases.
Other integrations still require their existing private software resources.

Source listings are read once per page refresh in a worker. Feature availability
and action discovery also run off the GUI thread; widget factories remain on it.
Repeated refreshes and selection changes cancel obsolete work and discard stale
results. Providers must be noninteractive and must not touch widgets. Cancellation
is checked between providers; filesystem calls must return before shutdown finishes.
Backend-owned credential context and selections are retained.

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


## Shared workers and API changes

Recent helpers are consolidated around `commonUtils.runtime.streams`,
`commonUtils.ui.operations.Operation` and `OperationProgress`. Download dialogs
reuse the same progress/cancellation widget; browser workers use the generic
worker module. New callers should use these canonical imports. Feature declarations
and direct file-type registration share resolution-rule validation.

Comic conversion, compression, organization and legacy metadata batch dialogs run
in workers with cancellation after the current comic. Separate ZIP creation checks
cancellation during assessment, hashing, writes and verification. Failures preserve
the affected source and are reported per item. Do not pass a batch cancellation flag
into an archive rewrite that must finish its current transaction.

Other integrations still have synchronous work; this change does not imply that
all Folders actions or external processes have cancellation support. See the
[UI ownership guide](features/UI_ARCHITECTURE.md#long-running-workflows-and-safe-closing)
and [commonUtils recipes](commonUtils/docs/RECIPES.md) before extending a workflow.
