# Develop Plex integration

Plex backs up and restores Plex Media Server application data and
compares movies and episodes across two database copies. See the
[user guide](../user/user.md) for the server workflows.

## Try a database summary change

On desktop, enable **Plex** and its required **rclone** feature in **Settings →
Features**. Launch Logistics from a terminal so you can see the report. Open
**Debug → Plex - Compare Databases…** and select two copies of the same Plex
library database. Expect matching counts for movies with a GUID and episodes
with a complete identity. For a synthetic input, use the four-table SQLite
schema in `PlexDatabaseTests.setUp()` in the test file below. The fixture has one
matchable movie, one matchable episode and an orphan episode.

`Python/features/plex/ui_contributions.py` connects this Debug action to
`database.test_script()`. For a small experiment, change the summary heading
`Metadata Item Matches` to `Matched items` in `diff_media_type()` in
`Python/features/plex/database.py`. Relaunch and repeat the comparison. The
terminal should show the new label for both media types with the same counts.
To check it without opening the app, add a test that captures stdout while
calling `database.test_script(self.path, self.path)` on the existing fixture
and checks the new heading and both sets of results. Run from the repository
root with the desktop environment installed.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_plex.py
```

Expect one movie match and one episode match from that fixture, with the
orphan in both unmatched episode lists. The existing tests cover read-only
SQLite access and duplicate matching as well as package and dialog behavior
with temporary folders and mocked external commands.

## Find the Manage PMS workflow

In desktop **Workspaces**, choose a local entry with the rclone credential
source that contains a matching `<folder>-PMSDATA` remote. In
`ui_contributions.py`, `_has_manage_pms()` checks the platform and selected
credential context, then passes the remote names to `detection.py`.
`_open_manage_pms()` lazily opens `ui/manage_pms_dialog.py`
(`PlexManagePMSDialog`). `folders.py` resolves the local and mounted package
folders without provisioning unrelated resources. `actions.py` connects the
dialog to `packages.py` for archive work. For transfer review and execution,
see [rclone transfers](../../rclone/development/transfers.md).

## Package and restore behavior

Stop Plex Media Server before packaging or restoring. Archive verification checks
that the archive can be read; it cannot make a live server database snapshot
consistent. Run under an account with access to the server data. Linux service
installations may need additional filesystem permissions and ownership handling.

- Windows exports the current-user registry settings and creates a split
  `pms_data.7z.001` archive using bundled 7-Zip. All commands use argument lists,
  check exit status and finish before reporting success. Root files are included
  along with subdirectories. The completed archive is tested before promotion.
- macOS creates `pms_data_mac.zip` and copies the server preferences plist.
- Linux creates `pms_data_linux.zip`. No macOS plist or Windows registry is used.
- New package files are staged and verified before replacing previous files.
  Unreadable source directories fail the package operation instead of silently
  leaving their contents out.
  Unrelated plist/registry files are retained. `PackagePublication` moves the old
  generation into a private recovery directory before promoting the new files.
  Ordinary failures restore the old generation. Conflicts or failed rollback
  retain originals and `journal.json` in `.logistics-plex-recovery-<id>` and report
  that path. Inspect it before explicit `PackagePublication.recover(path)` rollback;
  changed published files and occupied restoration targets are preserved for manual
  resolution. Recovery checks the complete generation before removing its published
  files and checkpoints their removal before restoring originals, so interrupted
  rollback can be retried without mistaking restored originals for external edits.
  The `rolling_back` journal phase also remains recoverable if the final commit
  checkpoint failed. A missing original backup stops recovery before published
  files are removed; the journal remains for manual resolution. Member moves use
  shared atomic no-overwrite rename, so a destination created after preflight is
  preserved rather than replaced. Multi-file visibility is not atomic. Committed
  cleanup failures report the retained directory without undoing the valid new
  generation.
- Restores extract into a temporary sibling directory before moving the current
  data aside. ZIP entries must stay under `Plex Media Server/`; linked content
  and overlapping data/package locations are rejected. Legacy macOS ZIP archives
  with that root directory remain readable. On Unix, ZIP restores preserve
  recorded file/directory permissions, excluding special permission bits;
  ownership still belongs to the restoring account.
- The previous data is retained as `Plex Media Server.previous-<id>` beside the
  restored data. Its location is logged. Check the restored server before
  removing this recovery copy. If the final directory move fails, Logistics
  attempts to restore the original directory.

`package_publication.require_package_ready()` blocks clear, sync, rebuild and
restore while the package directory retains recovery artifacts. Reviewed sync
checks again in `before_start`, so recovery that appears during review prevents
launch. The guard preserves the retained generation for explicit recovery.
`test_plex.py` and `test_plex_publication.py` cover blocked actions and the
launch-time recheck.

Staging and retained recovery data require additional disk space. Preferences
and Windows registry imports are separate from the data-directory swap; they
are not part of a single transaction. Native registry/7-Zip operations and Linux
service ownership still need validation on real installations.

## Platform locations

Default data locations use the current user's home directory on macOS and
`LOCALAPPDATA` on Windows, falling back to `~/AppData/Local`. Linux checks the
existing native, Flatpak and Snap data locations. Set
`PLEX_MEDIA_SERVER_APPLICATION_SUPPORT_DIR` to the **parent** of `Plex Media Server`
to use a custom location, including a not-yet-created restore destination.

## Database comparison

`database.py` reads SQLite in read-only mode and attaches media parts by
metadata ID. Missing optional columns become `None`; missing structural
columns raise an explicit error. Deleted items are excluded. Empty duration
totals are zero and nonempty totals retain fractional days. Photo filtering and
comparison of types other than movies and episodes raise explicit errors.

`comparison.py` matches movies by nonempty GUID and episodes by series GUID
or normalized series title, plus season and episode index. Missing parents or
indices leave episodes unmatched. Each duplicate can match at most once.
The optional hash check requires a nonempty shared media hash and can reassign
ambiguous pairs to match more compatible duplicates.

## Validation

The focused Plex test above also covers extraction failures, traversal and
failed directory replacement. To change publication or recovery behavior, also
run the synthetic journal and promotion-failure suite.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_plex_publication.py
```

It exercises retries, conflicts, no-overwrite moves and cleanup after a
committed package. Check native registry and 7-Zip behavior and Linux service
ownership on their respective installations.

## Desktop and mobile ownership

Both Manage PMS and database comparison run in desktop Qt. See the
[mobile support boundary](../user_mobile/user_mobile.md).
