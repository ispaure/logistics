# Git

Git is a repository workspace inside Logistics. Its branch icon appears after
Folder Hub and active Folder Actions/sync jobs, before Tools. When a dedicated Sync
destination is added, Git belongs below it too.
Enable or disable it under Settings like other features.

## Get started

Install **Git 2.40 or newer**. Logistics uses `git` from your PATH; **Git settings…**
lets you choose another executable and checks its version. Git is supplied separately
from Logistics.

- **Open…** selects an existing working repository, including a linked worktree.
- **Clone…** accepts an HTTPS/SSH URL or local repository path and a new or empty
  destination. You can choose a branch and initialize submodules recursively.
- **Init…** creates Git metadata in a selected folder while keeping existing files.

The repository selector remembers recent repositories. **Repositories…** pins or
removes bookmarks. Removing a bookmark keeps all repository files on disk.
Bare repositories can be remote destinations; open working repositories in the UI.

For private repositories, configure your Git credential helper or SSH agent first.
Set up SSH host trust outside Logistics. The app uses stored credentials and avoids
invisible terminal prompts. Use URLs without passwords, HTTPS credentials, or query
tokens. Authentication errors appear in the operation log.

## Everyday changes

The **Changes** tab separates **Conflicts**, **Unstaged**, and **Staged** files.
One file can appear in both staged and unstaged groups when you edit it after staging.
Select a file to inspect its diff; untracked text files show a bounded content preview.
Binary files show an explanation instead of text.

1. Select files and choose **Stage**. **Stage all** includes untracked files and deletions.
2. Use **Unstage** to remove selected changes from the index while keeping working files.
3. Enter a commit subject and optional description, then **Commit staged changes**.
4. If Git needs an author name/email, use **More… → Commit identity…**. This saves
   repository settings, shared with linked worktrees, without changing global identity.

Double-click a changed file, or right-click it and choose **Open working file in
Text Editor**, to use Logistics' existing Text Editor. Enable that feature in
Settings first. Saving refreshes Git; the normal document host handles unsaved edits.
Files resolving outside the repository are opened separately.

**Discard…** restores selected ordinary tracked files from the index. It leaves
staged changes in place. Review the listed paths: unstaged edits generally cannot
be recovered through Git. Untracked files, conflicts, renames, and submodule changes
need their own handling and are excluded from this action.

**Amend last commit** replaces the branch tip. Review the confirmation before
amending published history. Failed commits retain their message draft. Switching
repositories or closing the app asks before discarding a draft.

## History and branches

The **History** tab shows the commit graph, subjects, branch/tag decorations, authors,
dates, and hashes. Select a commit for its details, diff, and complete historical file
tree; select a file in that tree to inspect its contents. Submodule entries show the
recorded child commit. Merge previews use Git's normal merge display, which may not
show every individual parent comparison.

History starts with 200 commits. **Load 200 more commits** expands it up to 5,000.
Search filters the loaded page by message, author, hash, or ref. The graph is hidden
while filtering so omitted rows cannot imply false ancestry. **Find in preview**
searches the displayed text; Enter moves to the next match.

**Branch…** creates a branch at HEAD or the selected history commit and optionally
switches to it. Double-click a local branch to switch. Its context menu also offers
merge, rename, setting an upstream without pushing, and deletion of merged branches. Git refuses to delete unmerged or
checked-out branches. Remote branches offer creation of a local tracking branch.

**More…** provides merge, cherry-pick, revert, and comparison of the selected history
commit against HEAD. Cherry-pick/revert of merge commits require a mainline choice
and are outside this version's UI.

## Remotes and publishing

**More… → Add remote…** configures a name and URL. The remote's context menu can
fetch, edit its URL, or remove it. Removing a remote keeps the server repository.

- **Fetch** updates configured remote references.
- **Pull…** offers fast-forward only (default), merge, or rebase of the upstream.
- **Push…** pushes the current branch to its configured upstream. Alternatively,
  publish to a chosen remote/branch and set the upstream. No force push is used.

Ahead/behind counts reflect the last fetched local references. Fetch again to learn
about server changes. Push affects only the current branch and does not automatically
publish tags or other local branches.

**More… → Create tag…** creates a lightweight tag or an annotated tag with a message,
at HEAD or the selected commit. Right-click a tag to view its commit, push it to a
chosen remote, or delete the local tag. Remote tags are kept when deleting locally.

## Stashes, conflicts, and recovery

**Stash…** saves changes with a message and optionally includes untracked files.
The stash context menu offers Apply, Pop, and Drop. Apply keeps the saved stash;
Pop removes it after a successful application. Review the confirmation before Drop.

A failed merge, pull/rebase, cherry-pick, or revert can leave conflicts. The workspace
refreshes and shows the current operation and conflict files. Edit conflicts in the
Text Editor or another editor, stage the resolved files, then use **Continue**.
**Abort…** asks Git to restore the operation's starting state. Conflicts from stash
application are resolved/staged manually; there is no separate stash Continue action.

**More… → Recover from reflog…** lists the latest 100 HEAD movements and creates a
rescue branch at a selected commit. By default it keeps your current branch and
working files. This can preserve commits displaced by an amend or another history
operation while their objects still exist.

## Worktrees, submodules, and subtrees

Under **More…**:

- **Worktrees…** lists linked working directories, opens another one, or creates a
  new worktree for an existing branch not already checked out elsewhere.
- **Submodules…** shows recursive status, initializes/updates recorded child commits,
  adds a submodule by URL/path, or opens a child folder as its own repository.
  Commit child changes in the child repository, then stage and commit its updated
  reference in the parent. Git's transport/security settings remain in effect.
- **Subtrees…** offers Add, Pull, and Push for a relative prefix and upstream URL/branch,
  with optional squash for Add/Pull. The extension must be available in your Git
  installation. Successful mappings are remembered locally. Start with a clean
  working tree and review the target before pushing.

## Progress and first-version boundaries

The workspace runs one Git job at a time and displays progress in **Operation log**.
**Cancel operation** requests process-tree cancellation; partial clones and repository
changes already made can remain. The workspace refreshes after writes, including
failures. Closing waits for the worker to stop.

Use **Refresh** after changes made outside Logistics. Re-entering the destination,
Git operations, and integrated editor saves also refresh it. There is no scheduled
fetch or filesystem polling. Text previews are limited to 1 MiB and show truncation;
oversized structured responses report an error rather than silently losing entries.

This version has unified text diffs and whole-file staging. Hunk staging, interactive
rebase editing, reset/clean, merge-tool launching, LFS management, sparse/partial
cloning, worktree removal, and hosting-provider features are future additions.
