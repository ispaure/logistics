# Blue Hole consumer maintenance

`Python/features/blender/addons/bluehole.py` owns the managed preset integration. DEFAULT enables main with Deluxe off and `auto_update` on; missing update preferences also default to on. The remote resolver picks the highest compatible exact baseline for the channel, then a legacy branch. Auto-update checks head on launch and caches by commit, including same-commit reuse from the renamed 4.5.1 family. With auto-update off, a recorded compatible installation on the selected channel is retained without network or cache access. First installs, source changes from Local and channel changes still resolve GitHub. Preserve `legacy:BlueHole`. Local mode validates the checkout and uses a symlink or junction, ignoring the hidden update preference. Rollback moves the link itself. `AddonLibrary` saves source mode, checkout and auto-update per preset as they change. Addon checkboxes and Blue Hole enable/channel/Deluxe changes automatically publish the pending enabled set; projection is guarded against cross-preset writes. Saving pending metadata is allowed while Blender runs, while applying files still requires it to be closed.

Only `UpdateUnavailable` allows fallback to a recorded compatible installation with an entrypoint. Preserve installed branch, commit and version separately from intent. Keep custom environments under `addon-data/bluehole` on disable. Below 5.2.2, legacy Deluxe stamping keeps the first preferences backup. With auto-update on, network failures defer Deluxe changes until successful online resolution. From 5.2.2, Deluxe is runtime-owned.

When auto-update is off, legacy Deluxe changes use the retained installation’s
payload without needing its cached ZIP. A broken or incompatible recorded copy
fails validation instead of silently updating.

## Validation limits

From the repo root, run:

```sh
python3 dev.py test desktop --exact-file Python/tests/blender/test_blender_bluehole.py
```

`test_blender_library.py` covers rollback, fallback, disabled updates, branch/source changes and retained Deluxe payloads. `test_blender_page.py` checks the source picker, GitHub-only update control and per-preset persistence. Native registration and export acceptance on 5.2.2 remains incomplete. See [controls and recovery](../user/user.md).
