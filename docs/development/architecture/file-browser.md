# File browser development

`Python/desktop/file_browser.py:BrowserView` installs enabled
`registry.get_browser_extensions()` on commonUtils FileBrowser. Shared APIs and
examples live in the [feature guide](https://github.com/ispaure/commonUtils/blob/main/ui/features/README.md).
Embedded and standalone Workspace hosts keep bindings with each view on detach.

## SQLite inspection boundary

Inspect SQLite is an explicit action. Only approved ordinary local files can
enable editing. Managed indexes and job databases stay read-only. Access checks
refuse protected roots, network mounts, links and unsupported providers.
Mobile has no SQLite editor. A dirty SQLite close veto keeps its browser attached
and runs before feature shutdown. Check `test_sqlite_browser_host.py`.
[Shared SQLite browser](../../../Python/commonUtils/docs/development/reference/ui/sqlite_browser/sqlite_browser.md)

## Directory-index admission and foreground demand

| Surface | Admission and freshness |
| --- | --- |
| Desktop Files | Open/navigation reconcile the visible folder. Refresh covers the subtree. Search/size views read snapshots. |
| Mobile Files | Opening Search or moving its location prepares the ordinary-local scope. Settled typing reads saved results or joins missing preparation. |
| Notes filename search | Settled nonempty queries validate the library root. Navigation supplies priority hints. |
| Notes navigation, calendar, body search and links | Provider-owned listings, bounded inventories or specialized reads. |

Desktop launch owns `IndexService`. Mobile scenes lease one app-private runner,
which starts on first scan. The last close requests retirement. Files and
ordinary Notes filename queries share the coordinator and adjacent durable
SQLite queue. Private, virtual and remote providers stay outside the ordinary
index. LocalCrypt may reuse credential-bound sealed name records.

Foreground hints settle after 150 ms. Unrelated work can yield after 500 ms and
gets a fair turn after five seconds, with longer retry turns for atomic commits.
Snapshot reads can proceed during writes. Mobile publishes validated batches,
rejects stale route/privacy generations, marks partial results and falls back
to live search after corrupt reads.

Use separate cancellation for mobile search preparation and query delivery.
Navigation, close and privacy transitions retire their hints. Hidden or locked
hosts pause admission while an active sibling can keep working. Prepared
snapshots can be partial. Each result batch checks that files still exist and
meet the current provider boundary. Test alongside Notes filename searches when
changing the shared queue. Covered descendant requests can follow an ancestor
job. Reader snapshots use separate SQLite connections.

The ordinary coordinator keeps `directory-index.jobs.sqlite3` and
`directory-index.jobs.lock` next to the index. Mobile's index lives under
app-private `Cache/`. LocalCrypt name records belong to the credential's
`Cache/LocalCryptNames` store.

## Add a format, panel and context action

1. Keep the File subclass cheap. Return `BrowserPanel` declarations whose worker
   loaders produce `BrowserDetails`; thumbnail sizes use physical pixels.
   Reuse folder scan counts. GUI actions own any prompt.
2. Export `register() -> Feature` from the feature package. Declare deferred
   `FileType` entries, `SelectionAction` and `FileActivation` in a `BrowserExtension`.
   Use `file_type_overrides` with a subclass to replace a shared type. Folder
   activation keeps navigation. First matching file activation wins.
3. Actions receive accepted selections. A right-click on an unselected entry
   targets it alone. Domain validation, recursion and deduplication stay with
   the handler. Recheck eligibility before running. Put rename actions in the
   `rename` category and refresh affected files after writes.
4. Use `create_controller(host)` for per-view state. Disablement removes future
   actions and type rules, while the retained binding finishes open work.
   Run `prepare_close()` and browser `stop()`; delay destruction until `idle`.

For a desktop example, follow Archives' registration to Extract
(`SelectionAction`), ZIP/TAR open (`FileActivation`) and per-view controller.
Comics retains CBZ activation. Run
`python3 dev.py test desktop test_file_browser_window.py` and expect contributions
to follow feature toggles and close to wait for retiring jobs.
[Archives owner](../../features/archives/development/development.md)

Workspaces mounts the same browser for selected local/private/remote sources with
credential and generation checks. Its **Show Legacy (session only)** toggle is
process-local and starts unchecked. Core Markdown activation enables editing.
Help uses preview by default, with Alt as the explicit edit path.
[Folder source contract](features.md#remote-folder-source-context)

Desktop regular and provider views share list, tile and column presentation.
Logistics retains credential policy, reader routing and feature cover loaders.
[Shared item presentation](../../../Python/commonUtils/docs/development/reference/ui/resource-providers.md#shared-item-presentation)
