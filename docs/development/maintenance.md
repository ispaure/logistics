# Maintenance priorities

For readability audit completion and its remaining native gate, use the
[current implementation status](maintenance/remaining-work-audit.md). The platform
and live-integration acceptance below remains separate.

The generic application shell now has isolated regression coverage for feature
initialization, folder sources, page lifecycle, and action dispatch. The larger
remaining maintenance risks are in external integrations, where validation needs
representative fixtures and platform checks before behavior changes.

## Integration workflows

- **Plex:** read-only database access, episode/GUID comparison and staged package/
  restore handling now have fixture coverage. Validate Windows registry/7-Zip,
  stopped-server restore, large packages, Linux ownership and multi-file recovery
  conflicts on real installations. Recovery copies intentionally
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
  explicit dependency updates remain separate from ordinary downloads.
  Downloads, explicit updates and season transfers now use cancellable workers.
- **FUSE:** command construction, timeout handling, recovery and conservative
  cleanup now have simulated-state coverage. Actual mounting still requires
  macOS, Windows and Linux driver validation. Mount paths separate configuration
  identities; a process-owned credential binding gates reuse and automatic recovery.
  Unknown or changed bindings require explicit unmounting, including mounts inherited
  after restart. Windows stale-mount recovery remains a separate follow-up.
- **Media renaming:** CSV plans use the shared rollback-capable rename engine.
  Fixtures cover duplicate chapter numbers, invalid filenames and failed publication.

## Folder discovery and presentation

`LogisticsConfig` creates independent resource directories at the checkout root
by default. Software/FFmpeg lookup, document labels, connection roots, Plex data
paths and mount-path calculation use `create_resources=False` to resolve paths
without creating Software or credential folders. Folder discovery also opts out
of those unrelated resources while retaining its existing Server/Local bootstrap.
Optional `[Resources] software_path` and `credentials_path` entries in
`configFile.ini` override them independently (relative to the checkout, or absolute).
Dropbox is never selected implicitly. Public binaries/installers are pinned in
`software_manifest.json`; `services.software` supplies project policy to the shared
`commonUtils.runtime.streams.downloads` and `commonUtils.ui.tasks.download` provisioning code. Download
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

Run `python3 dev.py test desktop` from the repository root for isolated desktop
regressions, or select a focused filename pattern; use `py` on Windows. These tests use
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
`commonUtils.ui.tasks.operations.Operation` and `OperationProgress`. Download dialogs
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
[UI ownership guide](architecture.md#long-running-workflows-and-safe-closing)
and [commonUtils recipes](https://github.com/ispaure/commonUtils/blob/main/ui/operation_progress.md) before extending a workflow.

## Ownership refactor validation (2026-10-22)

Final isolated runs passed all 179 desktop, 179 commonUtils and 162 mobile test
files. Focused follow-up coverage checks Plex promotion/journal failures and
malformed or linked recovery members, FUSE credential changes and refusal to
probe unknown mounts, subprocess worker startup failure, and logger option isolation.
Packaging, lint, architecture, compatibility, toolchain and source hygiene checks
also passed. Extracted LM actions, folder projection and provider-opening bodies
match their previous syntax trees after normalizing owner access and inlining view
construction.

Comics comparisons against the pre-refactor baseline passed 80 cleanup/error
traces, 24 byte-identical encodings and 32 full plain/encrypted compression runs,
including extraction, staging, final manifests and keep/delete behavior. These
comparisons were repeated after the coordinated archive changes.

Blue Hole remains a separate repository. Its exact committed commonUtils vendor
copy passed membership and byte comparison, 25 consumer tests and 24 vendored
Perforce tests. Save remains permissive when checkout fails; export still obeys
its error policy. No live Blender, Perforce server, mount-driver or mobile-device
validation is claimed by these host checks. No temporary Boox apps were installed.

## Follow-up recovery and consumer review (2026-10-22)

Plex recovery now preflights the whole generation, journals rollback progress and
can resume after partial restoration or a failed final commit checkpoint. Missing
originals stop recovery without deleting published files or the journal. Package
promotion, backup and restoration reuse shared atomic no-overwrite rename, preserving
files that appear after the destination preflight. A committed cleanup failure
retains the valid new generation and cannot be recovered as an uncommitted package.

The expanded Plex suite passes 36 tests, including every publication replacement
failure, failed rollback checkpoints, external destination races and missing
backups. The new conflict/retry cases were also run against previous implementations
to reproduce their failures before checking the fixes.

A second complete isolated pass passed all 179 desktop, 179 shared and 162 mobile
test files. Comics comparisons again matched 80 cleanup/error traces, 24 encoded
outputs byte-for-byte and 32 full plain/encrypted archive runs. Lint, architecture,
source hygiene, toolchain, compatibility, packaging and documentation checks pass.

Blue Hole development and add-on metadata now target Blender 5.2.2 on
`blender-5.2.2/alpha`; the local legacy 4.5.1 branch is unchanged. Its 26 consumer
tests and 24 actual-vendor Perforce tests pass. Vendor verification compares pinned
Git content with checkout line-ending normalization, rather than comparing against
unfinished upstream edits. Missing, stale, changed and linked members still fail.
Shared UI wording now names the host generically and labels existing character
limits correctly. No native Blender, Perforce server, mount-driver or mobile-device
validation is claimed. The shared audit retains the separate volume-identity and
offline-index policy concern; this follow-up does not change that contract.
