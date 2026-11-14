# Blue Hole consumer maintenance

`Python/features/blender/addons/bluehole.py` owns the managed preset integration. DEFAULT enables main with Deluxe off. The remote resolver picks the highest compatible exact baseline for the channel, then a legacy branch. Enabled launch checks head and caches by commit, including same-commit reuse from the renamed 4.5.1 family. Preserve `legacy:BlueHole`. Local mode validates the checkout and uses a symlink or junction. Rollback moves the link itself. `AddonLibrary` saves the source mode and checkout per preset as they change. Save Addon Selection publishes the enabled set.

Only `UpdateUnavailable` allows fallback to a recorded compatible installation with an entrypoint. Preserve installed branch, commit and version separately from intent. Keep custom environments under `addon-data/bluehole` on disable. Below 5.2.2, legacy Deluxe stamping keeps the first preferences backup and waits for online resolution. From 5.2.2, Deluxe is runtime-owned.

## Validation limits

From the repo root, run:

```sh
python3 dev.py test desktop --exact-file Python/tests/blender/test_blender_bluehole.py
```

`test_blender_library.py` covers rollback and fallback. `test_blender_page.py` checks the local source picker and per-preset persistence. Native registration and export acceptance on 5.2.2 remains incomplete. See [controls and recovery](../user/user.md).
