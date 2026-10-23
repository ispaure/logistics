# Readability and organization rehabilitation

## Scope and priorities

The October 23 follow-up prioritizes human navigation, cohesive ownership and
readable code over more reliability-only changes. Work stays local: no pushes,
release retries or release monitoring. The release heartbeat is paused. The
existing Perforce consumer/build architecture is preserved.

The starting point is Logistics `71a222e4`, commonUtils `922ae02b`; concurrent
mobile navigation and shared browser/index work remains in the primary checkout.
An isolated worktree protects those edits. The original architecture audit and
validation history remain available; they are not current proof for new changes.

| Starting navigation hotspot | Tracked Python files in one directory |
| --- | ---: |
| Mobile build root | 27 |
| Mobile host tests | 163 |
| Native UI checks/probes | 99 |
| Logistics mobile host | 99 |
| Shared regression tests | 185 |

These counts identify where to inspect responsibility boundaries. They are not
file-count targets: do not split cohesive code or move source merely to improve a
number. Generated artifacts, third-party vendors and the Perforce payload retain
their established ownership.

## Completed work

### Generated-project and artwork adapters

Six related files now live in `mobile_build/build_support/`. The bridge builder
imports their composition explicitly. Updated callers, source-relative asset
paths and artwork-generation commands retain the same behavior. The
[tooling owner map](../build-tooling.md) explains where each task belongs.

Validation: app icon, privacy, scene and Android reader build contracts passed.
The first combined command omitted the mobile test directory from PYTHONPATH,
so the camera fixture could not import its sibling; the next desktop-environment attempt lacked Toga. Camera checks then pass in
the existing mobile host environment. All 13 other focused adapter cases and
five wiki-layout cases pass. CLI import/help smoke checks pass. No native SDK build is claimed by these host fixtures.

### Local deployment and distribution

Twelve related modules now live in `mobile_build/deployment/`. Their package
imports replace duplicated script/module import fallbacks. The existing six
Finder launchers, canonical credentials and generated workspaces retain their
locations. Module subprocesses start from the repository root, including the
parallel platform workers and deployment window.

All 63 deployment cases pass across the existing desktop/mobile host environments;
the desktop environment lacks cryptography, so the ten JWT/distribution cases run
in the existing mobile environment. Real worker overlap and separate workspace
contracts still run. A launcher fixture checks all six shell entry points from an
unrelated working directory. No device install, upload or notification was run.

### Native validation tools

Six native evidence/fixture drivers now live in `mobile_build/validation/`.
The build root has three Python entry points instead of 27 mixed-purpose files.
Twenty report, workflow/gate and reader-resume tests pass; actionlint, Ruff and
CLI help checks pass. No device validation or release rerun is claimed. Existing
native test source and generated report locations remain unchanged.

## Next work

Consolidate the wiki
under each repository's root `docs/`. Keep H1 page titles and linked same-named
folder landing pages so the Markdown viewer presents a navigable tree. Preserve
short compatibility entry links where applications or saved links depend on them.
