# Develop Plex integration

## Try a database summary change

From a terminal, launch desktop Logistics with Plex and rclone enabled. Open **Debug → Plex - Compare Databases…** and select two copies of one database. Change `Metadata Item Matches` to `Matched items` in `Python/features/plex/database.py:diff_media_type`. In the existing SQLite fixture, capture stdout from `database.test_script(self.path, self.path)`. Run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_plex.py
```

Expect the new heading, one movie and one episode match, and the orphan episode unmatched on both sides.

`database.py` opens SQLite read-only, defaults missing optional columns to null and rejects missing structural columns. `comparison.py` pairs movies by GUID and episodes by series identity, season and index. Optional hash matching still pairs each duplicate at most once.

## Package and restore behavior

**Manage PMS** requires a matching `<folder>-PMSDATA` remote under the selected credential context. `ui_contributions.py` opens the dialog, `folders.py` resolves paths, and `packages.py` handles files. See [rclone transfers](../../rclone/development/transfers.md).

Stop Plex before packaging and restoring. Use an account that can access server data. Windows creates split `pms_data.7z.001` and exports registry settings. macOS creates `pms_data_mac.zip` and copies its plist. Linux creates `pms_data_linux.zip`. `PLEX_MEDIA_SERVER_APPLICATION_SUPPORT_DIR` points to the parent of `Plex Media Server`.

Stage and verify before publication. Unreadable source directories fail. `PackagePublication` keeps the old generation in `.logistics-plex-recovery-<id>`. Conflicts or rollback errors retain it and `journal.json`. Inspect before explicit `PackagePublication.recover(path)`. Recovery checks originals before removing published files and preserves changed files or occupied targets for manual resolution. No-overwrite moves and checkpoints support retry. Committed cleanup failure retains recovery data. Block clear, sync, rebuild and restore on recovery artifacts. Reviewed sync rechecks at launch.

Restore to a sibling staging directory. Reject overlap, links and ZIP entries outside `Plex Media Server/`. Keep legacy macOS archives readable. Unix restores modes without special bits. Keep logged `Plex Media Server.previous-<id>` until the server checks out. If final move fails, attempt to restore the original. Preferences and registry imports occur separately.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_plex_publication.py
```

Expect promotion and rollback retries to preserve originals and concurrent changes. Native registry, 7-Zip and Linux service ownership require host checks. See [operator workflows](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).
