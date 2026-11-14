# Blue Hole consumer maintenance

Change the Blue Hole source, version compatibility or installed-copy recovery
from **Blender → Configure Blender… → Presets → Blue Hole**. Blue Hole's add-on
internals, operators, export policy and vendored dependencies belong to that project.
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

For **Local**, `local_checkout()` validates the chosen Git working tree and
`local_addon()` checks its metadata against the managed release. Apply uses a
directory symlink or Windows junction to the checkout. Copying a preset keeps
the choice and recreates the link on launch. Rollback moves the link itself,
and switching to GitHub replaces it with a real directory. The checkout lives
outside the preset and local mode skips GitHub.

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
For releases below Blender 5.2.2, Logistics can stamp Deluxe preferences and
keymaps when the payload digest changes, keeping the first pre-Deluxe preference
backup if there was a preference file. Previously stamped files remain after
turning Deluxe off. From 5.2.2 onward the add-on handles Deluxe at runtime and
Logistics drops the legacy stamp setting from pending and applied state.

## Validation limits

Run from the repository root after [desktop setup](../../../development/getting-started.md):

```sh
python3 dev.py test desktop --exact-file Python/tests/blender/test_blender_bluehole.py
```

Expect 14 passes. The file supplies mocked remote branch and commit responses
for version/channel routing, commit cache reuse, unsafe and incompatible
archives, environment preservation and legacy Deluxe boundaries.
`test_blender_library.py` covers transactional updates, disable/re-enable,
rollback and installed-copy fallback; `test_blender_page.py` covers requested
versus installed state and the offline warning.

Current remote branch availability and native add-on registration, operator UI,
theme/keymap correctness and exports require separate runtime checks. Blue Hole
acceptance on Blender 5.2.2 remains incomplete.
