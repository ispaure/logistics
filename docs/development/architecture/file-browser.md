# File browser development

`Python/desktop/file_browser.py:BrowserView` installs enabled
`registry.get_browser_extensions()` on commonUtils FileBrowser. Shared APIs and
examples live in the [feature guide](../../../Python/commonUtils/docs/development/reference/ui/features/features.md).
Embedded and standalone Workspace hosts keep bindings with each view on detach.

## Moving files and folders

The desktop host owns file-drop targets and spring-loaded folder and tab
navigation. Ordinary and LocalCrypt browsers use the same move controller,
including in detached workspaces. It retains provider leases through completion.
Mobile File Browser captures selected revisions, then runs each cut item through
the existing move and document-mutation worker.

The shared provider mutation verifies staged cross-provider copies before source
cleanup. A completed ordinary local move reconciles Home references and durable
reader checkpoints. A protected route retires old opening references after
confirmed removal and keeps reading state within its original storage. After
partial source cleanup, only confirmed removals retire old Home references.

### Native desktop exchange

`Python/desktop/browser_drop.py` recognizes local-file URLs on the same
folder, tab and detached-window targets. Qt maps `text/uri-list` to file URLs
on macOS and `CF_HDROP` on Windows. Dolphin consumes the URI list on Linux.
The path list may contain multiple files, folders or both. Finder file promises,
Explorer virtual-file descriptors and Dolphin URLs without local paths fall
outside this contract. Local provider copies require independent regular
files and ordinary folders, within the shared inventory size and depth limits.

Native imports acknowledge receipt as a copy so the source cannot interpret an
asynchronous drop as permission to delete data. Logistics performs the
requested move through its verified provider mutation. Sources offering only
a move or link are rejected. Partial results, conflicts and cancellation appear
in the desktop Workspace actions process view. Native local exports offer
durable file URLs and leave file-manager transfer progress and conflict
handling with the receiver. On Cocoa, Qt can return an ignored action after
Finder completes a drop. Logistics reports an unknown outcome in that case.
Logistics cannot reconcile Home references with an external move because the
receiver does not report the final destination to the browser.

LocalCrypt drag payloads stay inside Logistics. The explicit **Prepare
Selected Items to Drag…** action in protected and remote tabs publishes
user-approved readable copies in a chosen ordinary folder. Logistics owns the
unpublished staging paths and removes them on normal cancellation or failure.
The user owns the published files. Their locations stay valid for asynchronous
file-manager reads. Drag preparation uses non-resumable rclone downloads and
the existing credential checks. A forced credential revocation can block
provider cleanup and leave an encrypted temporary item in the provider.

On import, a copy builds a `.drag-…` tree and a cross-provider move builds a
`.transfer-…` tree. LocalCrypt also prepares each new file under a
`.create-…` name. Process exit before the final rename can leave a verified
stage. Exit after a move publishes but before source removal can leave both
complete copies. A retry must respect the destination collision.

LocalCrypt leaves abandoned stages alone on fresh unlock. A sealed ownership
record can identify an earlier revision. Removal still acts on a pathname,
which another writer can replace after the revision check. Preparing a
complete tree outside the mirror keeps it out of transfers of that mirror.
On macOS, a second process running as the same user could write in that
owner-only staging directory while Logistics held its advisory lease.
Exclusive rename protects an occupied destination and accepts the current
source pathname.

To prevent leftovers safely, the provider needs to own the encrypted tree
from allocation through verification and publication. It must exclude other
writers or atomically publish the verified immutable tree into the authorized
destination without overwriting. Recovery after revocation requires a fresh
grant and retirement tied to the owned object. A free lease alone cannot
distinguish a crash before publication from one after it. Historical stages,
replacements and move sources must survive an ambiguous outcome.

The desktop browser tests exercise real Qt widget dispatch with generated URI
lists. They cover action and volume selection, nested bytes, collisions,
cancellation, path handoff, encrypted imports, and remote export preparation.
Native desktop acceptance also requires testing the real drag in both
directions with Finder, Explorer and Dolphin, including actual cross-volume
behavior and file-manager conflict or cancellation results.

The desktop File Browser host tests cover hover, Escape, window arrangements
and keyboard actions. The mobile destination and document-mutation tests cover
conflicts, interrupted cleanup, and Home references. The managed
`workspace-move` probe exercises the native mobile file menus and LocalCrypt.
On iPhone it also moves a generated EPUB and CBZ together, relaunches the app,
and reopens both from Home to verify the EPUB bookmark and comic page 37.

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
| Mobile Files | Settled typing searches the selected folder and descendants using guarded filename snapshots. |
| Notes filename search | Queries validate the library root. Mobile Notes shares ordinary physical folder snapshots with Files and Documents. Desktop navigation supplies priority hints. |
| Notes navigation, calendar, body search and links | Provider-owned listings, bounded inventories or specialized reads. |

Desktop launch owns `IndexService`. Desktop Files and ordinary Notes filename
queries share that coordinator and durable SQLite queue. Mobile Workspaces,
Documents and Notes share `Cache/device-filenames.sqlite3`, which stores
provider-guarded folder snapshots. Paths in the results follow each provider's
root. Private, virtual and remote providers stay outside that database.
Unlocked LocalCrypt views share their credential-bound sealed name records.

Foreground hints settle after 150 ms. Unrelated work can yield after 500 ms and
gets a fair turn after five seconds, with longer retry turns for atomic commits.
Snapshot reads can proceed during writes. Mobile rejects stale route and privacy
generations, validates hits, marks partial results, and can scan live when the
disposable cache is unavailable.

Use separate cancellation for mobile search preparation and query delivery.
Navigation, close and privacy transitions retire their hints. Hidden or locked
hosts pause admission while an active sibling can keep working. Prepared
snapshots can be partial. Actions on provisional saved rows recheck the
provider. A cold scan loads full metadata only for matching rows. Reconciliation leaves a pending typing delay in place and replays an already-submitted query without another delay. Test alongside Notes filename searches when
changing the shared queue. Covered descendant requests can follow an ancestor
job. Reader snapshots use separate SQLite connections.

The desktop list sorts using filenames from the live Qt model. It sizes the
metadata columns using the visible rows, and fetches folder totals through the
shared index worker.

The desktop coordinator keeps `directory-index.jobs.sqlite3` and
`directory-index.jobs.lock` next to its index. Mobile startup retires the former
app-private coordinator database and its sidecars. LocalCrypt name records
belong to the credential's `Cache/LocalCryptNames` store. Mobile keeps a
separate SQLite cache per copy and credential package. SQLite stores opaque
keys and credential-sealed batches. Filename data is decrypted for search
under the active credential, and retention stays within that copy's cache.

### Desktop process lifetime

Each app process participates in the same durable index queue without a launch
lock. The OS coordinator lock elects a runner and the writer lock serializes
mutations. A browser drops its own subscription on close. App exit drains the
worker, releasing SQLite and locks. A later launch can resume unfinished index
requests.

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
