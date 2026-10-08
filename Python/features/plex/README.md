# Plex Feature

For usage instructions, see the [user guide](user_docs/index.md). This README
covers development, implementation details and validation.


Provides Plex integration for Logistics.

## Using this feature

Select a local folder with a paired PMSDATA remote in **Folders**, then open
**Manage PMS…**. Database comparisons are a separate **Debug** workflow.

See [shared setup and resource paths](../../../CONFIGURATION.md) and the
[Logistics feature index](../../../README.md#features) for application-wide setup.

## Responsibilities

- Detect folders with a matching `-PMSDATA` rclone remote.
- Back up and restore Plex Media Server application data.
- Support Windows split 7-Zip packages and macOS/Linux ZIP packages.
- Compare selected Plex database copies through Debug.
- Keep Plex-specific behavior outside Logistics core and generic UI code.

## Structure

- `detection.py` detects Plex PMS support and platform data locations.
- `folders.py` resolves local and mounted `-PMSDATA` helper folders.
- `actions.py` exposes package/restore actions and optional user-facing error messages.
- `packages.py` stages archive creation and extraction before replacing existing data.
- `database.py` reads SQLite databases in read-only mode and resolves media/episode relationships.
- `comparison.py` matches GUIDs or episode identities without losing duplicate entries.
- `ui_contributions.py` contributes Manage PMS to matching folders and the database test to Debug.
- `__init__.py` exposes the feature to the Logistics feature registry.

## Manage PMS

A local Logistics folder receives the Manage PMS workflow when a matching
`<folder>-PMSDATA` rclone remote exists.

The workflow supports:

- Opening local and mounted `-PMSDATA` locations.
- Clearing the local package.
- Pulling the remote package locally.
- Unpacking the local package into the platform Plex Media Server data location.
- Packaging current Plex Media Server data locally.
- Pushing the local package to the paired remote.

Plex intentionally depends on rclone for these backup and restore sync operations.

## Initialization

This feature does not require startup initialization.

It is discovered by the Logistics feature registry and performs no work until
Plex functionality is used.

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
  Unrelated plist/registry files are retained. Promotion is per file, so a failure
  while replacing a split archive can leave a partly updated package; there is
  no transaction covering all package files.
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

Debug's **Plex - Compare Databases...** asks for two database copies instead of
assuming personal paths. Movies match by nonempty GUID; episodes match by series
GUID (or normalized series title when no GUID exists), season and episode index.
Missing parents/indices remain unmatched. Duplicate entries match at most once,
and optional hash checking requires a nonempty shared media hash. Ambiguous
duplicate pairs are reassigned when needed to maximize compatible matches. Deleted entries
are excluded from comparison; media parts are attached by metadata ID.

Absent optional database columns are returned as `None`; missing structural
columns raise an explicit error. Empty duration totals are zero and nonempty
totals retain fractional days. Photo filtering and comparison of other media
types remain explicitly unsupported instead of returning misleading empty results.

## Validation

`Python/tests/test_plex.py` uses temporary SQLite databases and package folders,
with external commands mocked. It covers extraction failures, traversal, failed
replacement/rollback, missing metadata, duplicate matching and dialog startup.
It does not operate on an installed Plex server.
