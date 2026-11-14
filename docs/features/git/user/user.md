# Git

Enable **Git** in **Settings → Features**, then open **Git** from the desktop
navigation rail. See [mobile availability](../user_mobile/user_mobile.md).

## Get started

Install Git 2.40 or newer. Logistics uses `git` on PATH, or the binary selected
in **Settings → Advanced → Git executable…**.

- **Open…** selects a working repository or linked worktree.
- **Clone…** accepts an HTTPS/SSH URL or local path and a new or empty destination.
  Choose a branch or recursive submodule initialization if needed.
- **Init…** creates a repository in an existing folder and keeps its files.

Use a tab’s **+** menu for these commands and **Bookmarks**. Drag a tab outside
the tab bar to detach it. Menus follow the active repository. Use Cmd/Ctrl+O to
open, Cmd/Ctrl+F to search, or Cmd/Ctrl+1/2/3 to switch views.

For private repositories, configure a Git credential helper or SSH agent and
establish SSH host trust first. Keep passwords and tokens out of URLs.
Authentication failures appear in **Operation log**.

## Everyday changes

1. Open **File status**, select a file and inspect its diff. A file can appear
   under both **Staged files** and **Unstaged files**.
2. Check files or choose **Stage file**. **Stage all** includes untracked files
   and deletions. **Unstage** keeps the working file.
3. Enter a subject and choose **Commit**. Set a repository author under
   **More… → Commit identity…** if prompted.

**Compare sides…** shows complete versions side by side. Use **Stage Hunk**,
**Unstage Hunk** or **Discard Hunk…** on a current, complete patch for an ordinary
tracked text file. Use file-level actions for untracked files, mode changes,
renames, conflicts, submodules or conversion filters.

**Discard…** restores eligible tracked files from the index and keeps staged
changes. Review the listed paths and check [backup settings](#git-preferences)
before discarding. **Amend last commit** replaces the branch tip. Failed commits
retain the draft. If **Push changes immediately to origin/{branch}** fails after
commit, retry **Push**. This option requires origin and an attached local branch.

## History and branches

Select **History**, then a commit and changed file to see its patch. Merge
commits compare against the first parent. Filter changed files by name or path,
click a parent hash to jump to that commit or browse **Full tree at commit**.
Use **Raw**, **Wrap** and **Ignore whitespace** to review patches. Staging a file
still affects all its changes.

**Uncommitted changes** shows pending changes against HEAD. The History filter
searches loaded commits. **Load 200 more commits** extends the view up to 5,000.

Use **Branch…** at HEAD or a selected commit, or double-click a local branch to
switch. Its context menu offers merge, rename, upstream and merged-branch deletion.
Remote branches can create local tracking branches. **More…** offers merge,
cherry-pick, revert, comparison against HEAD and **Create tag…**.

## Remotes and publishing

- **More… → Add remote…** saves a name and URL.
- **Fetch** updates remote references and incoming/outgoing counts.
- **Pull…** offers fast-forward only, merge or rebase.
- **Push** sends the current branch to its upstream. **Publish branch…** sets an
  upstream. **Push options → Publish to…** can replace it. Enable
  **Force push with lease…** in preferences to use it against the existing upstream.
- Right-click a tag to push it separately, or enable **Push tags with the selected branch**.

## Git preferences

Open **Settings → Feature settings → Git** or **More… → Git preferences…**.
**Options** controls refresh, pull strategy, previews and staging. Switch between
software defaults and personal settings. Use **↶** to clear a personal override.

**Accounts** supports secure HTTPS helpers and existing SSH agents. Saving account
removal also erases its helper credential. GitHub browser sign-in requires Git
Credential Manager. Review any helper or identity error before retrying a failed save.

**Advanced** controls discard backups, enabled by default. To restore a discarded
file or hunk manually, look in the repository’s Git metadata under
`logistics-backups/<id>/` and use `paths.json` to find the original path.

**Custom Actions** run in the repository with JSON string-array arguments, such
as `["status", "--short"]` for `git`. Arguments can contain `{repo}`, `{file}`
and `{commit}`. The worker passes arguments directly without shell expansion.

## Stashes, conflicts, and recovery

**Stash…** can include untracked files. **Apply** keeps the stash. **Pop** removes
it after successful application. **Drop** deletes it.

Double-click a conflicted text file to open its three-pane resolver. Pick a side,
keep both or edit the center result, mark the change resolved, then save and stage
before **Continue**. Resolve binary, delete/modify, symlink, submodule and filtered
conflicts manually. **Abort…** asks Git to restore the operation’s starting state.
For conflicts from stash application, resolve and stage manually.

Use **More… → Recover from reflog…** to create a rescue branch at a recent HEAD
position while keeping your current branch and files.

## Worktrees, submodules, and subtrees

Under **More…**, open **Worktrees…** to list, open or add linked checkouts. Use
**Submodules…** to inspect or update recorded child commits. Commit changes in
the child before staging its reference in the parent. **Subtrees…** needs your
installation’s subtree extension. Start with a clean working tree and check the
prefix, URL and branch before Add, Pull or Push.

## Progress and first-version boundaries

Follow one active job per repository in **Operation log**. Cancelling can leave
partial clones or completed writes. Inspect the refreshed state before retrying.
Use **Terminal** for interactive rebase, reset/clean, LFS or worktree removal.

## Repository settings and terminal

Repository **Settings** sets its commit template, remotes, signing and author.
Linked worktrees share local settings. **Terminal** opens at the repository root.

## Search repository history

**Search** queries message, SHA (at least four characters), branch, changed path
or author. Date filters include both endpoint days in local time. Narrow the
range if a large path search reaches Git’s output limit.

## Reviewing changes from editors

Double-click a file or choose **Open working file in editor** to open the current
disk file in its most specific registered IDE project or Text Editor. Historical
previews stay read-only. In IDE or Text Editor, click a change marker to inspect
or revert buffer lines or stage an eligible saved hunk against the index.

## Troubleshooting

Use **Refresh** for local changes and **Fetch** for upstream counts. Automatic
file watching covers up to 2,000 entries. If another instance changed preferences,
reopen Settings before editing again. For authentication errors, inspect
**Operation log** and check the configured helper or SSH agent.
