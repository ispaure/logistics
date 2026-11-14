# Git workspace

Inspect repository changes, review history and run Git operations on desktop.
The workspace requires Git 2.40 or newer. See the [user guide](../user/user.md)
for setup and authentication and [mobile availability](../user_mobile/user_mobile.md)
for the platform boundary.

## Try a diff preview change

On desktop, enable **Git** under **Settings → Features**, select **Git** in
the rail and open a disposable working repository from the repository tab's
**+ → Open…** menu. Commit a small file, then replace its contents with binary
data containing a NUL byte. In **File status**, select the modified file. The
formatted preview should show the binary-file notice.

For a small wording change, edit that notice in
`Python/features/git/diff_view.py` (`present_diff`).
`ui/preview.py` calls it for the formatted preview and retains the original
patch for **Raw**. Update the expected notice in
`test_added_deleted_binary_and_mode_only_files_have_friendly_details`.
Run from the repository root after [desktop setup](../../../development/getting-started.md):

```sh
python3 dev.py test desktop --exact-file Python/tests/version_control/test_git_diff_view.py
```

Expect six passing tests. The synthetic patches cover the formatted notice,
hunk ranges, line positions, truncation and preservation of the exact raw patch.
On relaunch, selecting the file should show the revised notice in the formatted
preview. Raw view should still show Git's original output.

## Find the owner

Paths below are relative to `Python/features/git/`.

| Change | Start here |
| --- | --- |
| Destination registration and retained repository tabs | `__init__.py:register` contributes `git.workspace` to the desktop shell. `ui/page.py` owns the dock-backed workspace and reuses an existing pane for an open repository. |
| File status, staging or preview | `ui/changes.py:build_file_status` creates the lists and commit composer. `ui/repository_view.py` owns snapshot publication, controls and retained preview selection. `ui/preview.py`, `diff_view.py` and `ui/hunks.py` own patch display and review. |
| History, search or reference navigation | `ui/history.py`, `ui/search.py` and `ui/navigation.py` build the views. `ui/history_controller.py:RepositoryHistory` owns paging and deferred selection. `graph.py` owns stable lane geometry as history grows. |
| Forms, mutation guards and Git behavior | `ui/commands/forms.py` collects input, `ui/commands/requests.py` captures it, and `ui/jobs.py` dispatches. `repository.py` owns Git queries and mutations, `models.py` parses machine output and `runner.py` runs Git. |
| Repository tools or settings | `ui/repository_tools.py` owns worktree, submodule and subtree dialogs. `ui/settings.py` owns repository settings. `ui/application_settings.py` and `ui/application_preferences.py` own feature preferences and their application to retained panes. |

The desktop shell supplies the rail and the close protocol. For contribution
and window ownership, see [desktop architecture](../../../development/architecture.md).
The feature uses commonUtils Workspace, CodeEdit and process helpers. Shared
library APIs are documented in the [commonUtils boundary guide](../../../development/commonutils-integration.md).

## Execution and lifecycle

One retained worker per repository pane serializes reads and writes, including
history queries. Each job uses a fresh runner, a cancellation event and a captured
repository path. Capture the path and, for branch-sensitive operations, the
expected branch before opening a modal form or menu. Dispatch rejects a changed
or closing view. `GitCommand` rechecks the repository and expected branch on the
worker. Index and worktree state can still change, so keep the backend's checked
patch and conflict validation.

Search completion also checks the query and limit that produced it. Refresh
requests coalesce while busy. After a write, refresh even on failure or
cancellation, since an unsuccessful merge can leave a valid conflict state.
Tab switching retains drafts, previews and logs. `prepare_close()` requests
cancellation and defers closing until the worker retires. A draft can veto
closing. Keep the thread owned until Qt emits `finished`.

## Command capture ownership

`GitRunner` uses argument arrays and literal pathspecs, and clears inherited
repository-location environment variables. The user's Git configuration, hooks,
signing, SSH and credential helpers apply. Terminal prompts are disabled. The
runner rejects HTTPS URLs with embedded credentials or query tokens and redacts
common credential forms in diagnostics. Sensitive credential-helper requests
use stdin and suppress both captured outputs.

The shared capture backend spools binary stdout and diagnostic stderr separately
and supervises stdin so cancellation and timeouts remain responsive. Machine
responses fail explicitly above 8 MiB. Text previews default to 1 MiB and
indicate truncation. The personal Diff preference supports 16–16,384 KiB.
The UI caps log size and long lines. Stderr progress streams on POSIX and
appears at completion on Windows.

Tracked branches push with an explicit `HEAD:<configured-upstream>` refspec and
automatic tag following disabled. Untracked branches open the publish form.
Detached HEAD and busy panes disable push. Force-with-lease requires a personal
preference and per-push confirmation. Review the operation log before retrying
any failed write. If commit succeeds and its optional push fails, the commit remains.

## History search

`Repository.search_history()` uses native Git searches over reachable history
with bounded output and paging. Path queries use NUL-delimited names. Commit
file lists compare against the first parent and handle root commits and deleted
files. Following a parent may load more history up to 5,000 commits. The History
view shows uncommitted changes separately. Those previews compare tracked files
with HEAD and use a bounded file read for untracked files or unborn repositories.

## Shared diff and merge UI

**Compare sides…** reads full text snapshots. **Resolve conflict…** reads the
ancestor, local and incoming index stages for the shared merge editor. Applying a
merge checks for concurrent edits and atomically saves the result. Before
optional staging, the adapter rechecks index entries and reads at most one byte
beyond the expected saved size. If the result changes, it remains unstaged for
review. Binary, delete/modify, symlink, submodule and conversion-filter
conflicts require manual handling. Hunk actions verify a complete current patch
before asking Git to stage, unstage or discard it.

Working-file opens from File status, History and Search use
`RepositoryView.edit_file`. They validate the current path even when the preview
shows a historical revision. The shell routes the request to a registered
[IDE project](../../ide/development/ide.md#implemented-contracts) when available,
with the enabled Text Editor and document host as fallback.

## Verified discard backups

With **Keep backups** enabled, `Repository.backup_files` checks file revisions and
SHA-256 digests, verifies the flushed private copies and rechecks every selected
path before publishing `paths.json` in Git metadata. A changed or newly created
file, corrupt copy or cancellation aborts discard. The checks are point-in-time.
Other editors can still write between the last check and Git's mutation.

## Repository settings

The toolbar's **Settings** button edits repository-local templates, remotes,
signing and identity. OK runs changes through the pane's worker. Linked worktrees
share the local Git config. Commands apply sequentially, so a failure can leave
earlier changes in place. Inspect the log and refreshed settings before retrying.
Templates live in Git metadata and populate empty composers while preserving drafts.

## Application preferences

`preferences.py` owns per-user `git.json`, including bookmarks, executable
selection, last repository and subtree mappings. `options.py` handles layered
INI defaults and command-scoped Git options. Optional index writes are disabled
for background status so they do not retrigger the watcher. An explicit
global-identity action writes global Git configuration. `accounts.py` delegates
authentication to native credential helpers or Git Credential Manager, with
secrets kept out of the settings schema.

## Settings writer conflicts

Preferences check the original JSON bytes before INI changes and again during
atomic JSON publication. A successful save advances the baseline, and
`adopt_saved` propagates values and baseline to retained panes together.
Reopen the workspace if another instance changed or deleted the file. INI and
JSON writes are separate, with optimistic conflict detection.

## Validation

In `Python/tests/version_control/`, use `test_git_backend.py` and
`test_git_merge.py` for mutation, backup, path and merge behavior.
`test_git_commands.py` covers stale repository or branch context.
`test_git_preferences.py` covers preference fanout, conflict handling and
credential-helper behavior. The UI, tabs, watcher and menu-retirement files
exercise retained panes, drafts, editor routing and shutdown.

Repository fixtures use local bare remotes. Only the submodule fixture opts
into local file transport. Subtree cases require Git's optional subtree command.
The UI fixture copies an initialized repository for each case so indexes,
refs and configuration stay isolated. Its Qt fixture drains owned work before
removing files. Native menu/docking behavior and real remote authentication
require runtime checks on the relevant desktop.
