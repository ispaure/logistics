# Blue Hole consumer maintenance

This guide covers Logistics' Blue Hole integration. Blue Hole's addon internals,
operators, export policy and its own vendored dependencies belong to that project.
For the full launcher architecture, see [Blender development](development.md);
for controls and recovery, see [Blender usage](../user/user.md).

## Configuration and remote resolution

`Python/features/blender/addons/bluehole.py` owns channel validation, branch
resolution, commit cache, installed-copy fallback, environment preservation and
Deluxe stamping. `DEFAULT` enables Blue Hole with main and Deluxe off. Preset
intent stores the channel separately from the installed branch/commit snapshot.

`resolve_branch()` reads a bounded, paginated branch catalog from the public
`ispaure/BlueHole` repository. It selects the highest exact Blender baseline at
or below the managed Blender version for the requested main/beta/alpha channel.
Legacy unqualified channel branches remain a fallback when no matching qualified
baseline exists. No compatible branch is an explicit failure.

`update()` rechecks the resolved branch head on each enabled launch, validates the
40-character commit and downloads by that commit. Cache entries live below
`addons/bluehole/<resolved-branch>/<commit>/addon.zip` in the manager root.
The renamed 4.5.1 family may reuse an old channel cache for the same commit.
Archive normalization keeps the stable `legacy:BlueHole` identity, with bounded
archive size/member count and regular library metadata/safety validation.
Browsing settings and saving intent do not call the remote update path.

## Apply and recovery

The regular addon apply transaction in `addons/library.py` owns resource backup,
verified package snapshots, preference preparation, rollback and publication.
Blue Hole is outside numeric shared-library selection. The installed snapshot
records the actual branch, commit and version independently of requested intent.

Only an `UpdateUnavailable` check/download failure admits installed-copy fallback.
It requires recorded ownership, a present entrypoint and declared compatibility;
a versioned branch newer than the managed Blender release is refused. Invalid
packages, no compatible branch and cancellation do not become offline success.
Fallback retains the installed snapshot and emits a warning; Deluxe stamping
waits for a successful online resolution.

On update, `envFiles/default` remains publisher-owned. Other existing environments
are preserved; disabling keeps them under preset `addon-data/bluehole` so a later
re-enable can restore them. These files follow preset copy/delete and rollback.
Deluxe writes preset preferences and keymaps only when its payload digest changes,
keeping the first pre-Deluxe preferences backup. Turning Deluxe off does not undo
previously stamped files.

## Validation limits

`Python/tests/blender/test_blender_bluehole.py` supplies mocked remote branch and
commit responses for version/channel routing, commit cache reuse, unsafe and
incompatible archives, environment preservation and Deluxe boundaries.
`test_blender_library.py` covers transactional updates, disable/re-enable,
rollback and installed-copy fallback; `test_blender_page.py` covers requested
versus installed state and the offline warning.

These contracts do not prove current remote branch availability, Blender addon
registration, operator UI, theme/keymap correctness or export behavior. Blender
5.2.2 addon acceptance remains incomplete. This audit used source/test review and
static documentation checks only; historical Blender runs in the developer guide
retain their original platform and date limits.
