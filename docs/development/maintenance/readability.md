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

### One root wiki per repository

Logistics feature documentation (107 pages) now lives in `docs/features/`,
including Bulk Rename. Feature Settings, header menus and mobile offline help
open the relevant article within the root Logistics sidebar. Source README and
user_docs compatibility links point there. Shared APIs remain in commonUtils.

commonUtils local commit `38c5d80` centralizes 65 guides, adds `docs/docs.md`, and
groups developer, API and user references. Seventy-nine shared wiki pages have
resolving local links; every folder has a linked landing and every page an H1.
Fourteen shared layout/catalog/real viewer cases pass. No Perforce runtime,
consumer build design or public Python interface changes.

Logistics passes five wiki-layout and four real desktop viewer cases, including
all built-in feature help buttons, folder landing rows and history. Fourteen mobile
host documentation/packaged-startup cases pass using a fresh disposable payload.
These verify that feature links retain the complete root sidebar and offline
articles. No native-device appearance claim is made.

### Regression tests grouped by subject

The 163 mobile host test files now live in nine coherent subject folders, with
four to 29 files per folder. Existing filenames and developer glob commands are
preserved. Cross-group fixtures use explicit package imports instead of depending
on sys.path ordering. The two browser DOM drivers stay with their contracts.

Both the complete pre-move and post-move suites discover the same 163 files and
1,169 cases with zero failed files. Each skips two browser DOM cases without Node;
both cases subsequently pass using the existing Node/Playwright/Chrome tools.
All moved tests are staged and trackable; `tooling/` deliberately avoids the
repository's generated `build/` ignore rule. No assertion or timeout was relaxed.

Blue Hole local commit `428f338` carries the exact shared documentation revision;
all 33 adapters and vendor membership/content checks pass. Production Python,
including all Perforce code, remains byte-identical to its prior consumer copy.

### Build declarations a reader can follow

The 82 required shared mobile supplements are one explicit declaration grouped by
domain, replacing the accumulated tuple extensions. The selected membership is
unchanged. Native project composition calls the camera, icon, scene and privacy
owners by module name; script/module mode is explicit rather than inferred from
an ImportError that could hide a broken import.

Real staging with the old and new declaration produces 979 byte-identical
members, including source manifests. The final tooling subset passes all 108
cases in 17 isolated files. Payload/wiki/developer-runner checks pass 26 cases;
the actual TestFlight workflow's five test module targets pass 39 cases. All 25
workflow/packaging cases run with one native Windows launcher skip (24 passes).
All workflow actionlint, configured Ruff and whitespace checks pass.

## Evidence-based assessment

| Dimension | Before this follow-up | Implemented result |
| --- | --- | --- |
| Readability | Mixed script ownership, accumulated build declarations and duplicated import guesses | Task-oriented owners, one shared-source declaration and visible native composition |
| Modularity | 27 root build scripts; 163 flat host tests | Three root entry points; three tooling owners and nine coherent test groups |
| Testability | Flat sibling imports relied on sys.path; old workflow module strings | Explicit fixture imports; stable filename selection; all 163 files still execute |
| Coupling | Existing feature/application boundaries | 24 host adapters / 15 feature edges / zero policy violations retained; no new runtime layer |
| Duplication | Nine deployment ImportError fallback handlers; scattered substantive guides | One deployment module context and one canonical guide per topic, with short legacy links |
| Consistency | Feature-local wiki roots and no shared docs landing | One H1-titled root wiki per repository with linked folder landings |
| Reliability | Existing runtime contracts and release blockers | Matching full mobile-host results, exact payload bytes and consumer checks; no assertion/gate weakened |

This establishes concrete navigation and maintenance improvements, not a new
whole-ecosystem quality score. Full native builds, native device behavior and
Blender 5.2.2 registration are not revalidated in this pass. The abandoned
release's failures are not fixed or relabeled as successful.

## Local commits and review locations

Logistics uses `codex/readability-build-owners`; commonUtils uses
`codex/readability-documentation` (`37bab64`); Blue Hole uses
`codex/readability-wiki` (`5eb4e35`). The shared branch is also available in the
canonical local shared repository, so the local Logistics pin resolves without a
remote. Concurrent primary-checkout edits have not been merged, reset or staged.
Nothing is pushed; the release heartbeat is paused.

## Next work

Native probe grouping needs a separately validated Briefcase/native-device pass;
its existing paths remain intact here. The 99-file native harness and remaining
large host modules deserve a distinct review of real lifecycle/ownership
boundaries rather than a filename-only split. Desktop and shared test groups preserve their independent consumer selection;
see the continuation record below. Keep the established Perforce build and vendor
architecture unchanged.

## Continued code readability pass

The next pass makes existing operation phases visible without adding packages
or changing public entry points. Shared image encoding (`f872be7`) separates pixel
preparation, sizing and metadata; eight contracts and 48 old/new real-image
profiles preserve bytes, failure/allocation order and source files. The affected
Logistics image/comic checks pass 120 cases.

Comic compression keeps one owning file and exposes sanitized-page collection,
collision validation, encoding and retention selection. All 194 comic cases in
11 isolated files pass. The existing version-comparison driver passes 32 complete
plain/AES runs across four layouts and two retention modes: extraction, sanitized
trees, staged results and final member hashes match `0d14ec7b`. Public settings,
statistics, logs, passwords, source checks and atomic replacement are unchanged.

Blue Hole `f5849bb` repairs a diagnostic NameError exposed by eight new preflight
contracts; `6dcc730` then separates message construction from ordered checks.
All 1,078 old/new profiles preserve outcomes, dependency order and exact diagnostic
text/popup flags relative to the repaired baseline. All 41 adapters pass. The
[consumer guide](../../features/blender/development/blue-hole-maintenance.md)
records the boundary and runtime validation limits. No Perforce build, environment
schema or source-control operation has been redesigned.


### Shared regression ownership and consumer selections

commonUtils `37bab64` groups 184 regression files into 15 subject folders.
Before and after, the complete isolated suite runs the same 1,250 cases with
zero failed files and 25 existing optional/platform skips. Root
`tests/qt_test_case.py` and `tests/mobile_smoke.py` retain their established consumer
paths. Every grouped package initializer is side-effect free. Four stale relative
test links surfaced during the first run; the corrected wiki and repeated full
suite pass. No test assertion was weakened.

Blue Hole `5eb4e35` contains the exact shared revision and retargets its existing
26 portable selectors to the owning test folders. All 41 adapter cases pass.
The selected portable suite passes 156 cases on host Python 3.11.8, with one
filesystem skip, against both shared source and Blue Hole's actual vendored copy.
This is not Blender embedded-runtime, registration or UI validation. The vendor
check confirms exact tracked membership and bytes, including the preserved
Perforce implementation. `5fbb146` also puts the public ordered preflight flow
before its private message helpers.

### Desktop regression ownership and wiki commands

Logistics groups 156 desktop regression files into 14 subject folders documented
in the [test owner map](../testing.md#desktop-test-folders). The 23 portable mobile
profiles, shared root fixtures and runner/testbed drivers keep their existing
paths. Cross-group fixture imports are explicit. An AST comparison verifies that
all 156 moved files retain their bodies and assertions after the required import
and source-path adjustments. All destinations are indexed; none fell through
an ignore rule.

The full mobile host suite still passes 163 files and 1,169 cases, with its two
optional DOM cases subsequently passing using existing offline browser tools.
The current wiki commands pass 48 desktop and 20 mobile cases; they now name the
actual grouped modules. Documentation remains in the root H1-titled wikis with
linked folder landings. Configured Ruff, architecture and toolchain checks pass;
indexed-source hygiene reports zero violations. No dependency was added.


The full desktop before/after runs each execute 179 files and 1,633 cases, with
zero failed files and the same 29 skips. Filenames, normalized case identities
and skip reasons match exactly. Skips require the pinned rclone executable or a
rebuilt host native bridge; neither runtime was installed for this pass. The
ordinary recursive `unittest discover` path also passes its focused build-version
checks. No assertion or timeout was relaxed. Test evidence stays under ignored
`test-results/`, outside this wiki.

### Continuation assessment

| Dimension | Before these continued units | Verified result |
| --- | --- | --- |
| Readability | Encoding, compression and preflight logic mixed preparation, policy and diagnostics | Same public entry points expose named phases and explicit inputs |
| Modularity | Flat desktop/shared regression directories | 14 desktop and 15 shared subject groups; testbed source paths retained |
| Testability | Consumer selectors and sibling fixtures depended on flat layouts | Explicit grouped fixture imports, exact case-set parity and retargeted portable selectors |
| Coupling | Existing shared allocation and consumer policies | Caller-owned image allocation, comic replacement and consumer preflight order preserved |
| Duplication | Diagnostic closures obscured the ordered operation checks | Cohesive same-file diagnostic helpers; no extra runtime layer |
| Consistency | Developer commands and source links named older module paths | Executable current wiki commands and root-wiki owner maps |
| Reliability | Diagnostic NameError on an invalid Blue Hole scene path | Eight behavior contracts protect repaired diagnostics; 1,078 parity profiles protect ordering/text |

This evidence supports these specific improvements. It does not establish a new
whole-ecosystem score or certify unavailable Blender/native runtime behavior.
Remaining high-value work is lifecycle ownership in the large mobile host and
native probe harness; moving those files requires appropriate platform validation,
not a filename-only reorganization. The abandoned release remains abandoned.


## Mobile application host continuation

### Workspaces tree ownership

The 165-line nested tree renderer mixed retained widget state with the folder
controller's discovery and credential policy. `FolderTreeView` now owns one
source tab's explicit row records, native identities and menu retirement. Its
callbacks declare the five host capabilities; the renderer has no application,
provider or credential reference. The host captures display inputs and mounts the
result. This is a runtime responsibility boundary, not another forwarding mixin.

The existing folder baseline passes 134 cases; after extraction, all 139 cases
pass including five new lifecycle/identity contracts. Seventeen responsiveness,
workspace-menu and staged-startup checks pass. Across 720 deterministic old/new
snapshots, hierarchy, styles, accessibility, icons, ordering, geometry, row reuse
and retired-menu states match the original renderer at `a66162df`. Native backend
styling implementation is unchanged; no new native device run is claimed.
The first new fixture incorrectly used `asyncio.run` on Toga's already-created
Task; corrected asynchronous test methods await the real handler contract.
