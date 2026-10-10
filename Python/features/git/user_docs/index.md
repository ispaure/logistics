# Git

Git is a repository workspace inside Logistics. Its branch icon appears after
Folder Hub and active Folder Actions/sync jobs, before Tools. When a dedicated Sync
destination is added, Git belongs below it too.
Enable or disable it under Settings like other features.

## Get started

Install **Git 2.40 or newer**. Logistics uses `git` from your PATH; **Settings → Advanced → Git executable…**
lets you choose another executable and checks its version. Before opening a repository,
Settings opens Git preferences directly. Git is supplied separately
from Logistics.

- **Open…** selects an existing working repository, including a linked worktree.
- **Clone…** accepts an HTTPS/SSH URL or local repository path and a new or empty
  destination. You can choose a branch and initialize submodules recursively.
- **Init…** creates Git metadata in a selected folder while keeping existing files.

Each open repository has its own tab. Switching tabs preserves commit drafts,
previews and operation logs. Drag horizontally to reorder, or outside the tab bar
to detach; its toolbar and repository controls travel with it. Use **+** for a new
pane. On narrow panes, the toolbar overflow menu keeps actions reachable.
Recent repositories are available under **+ → Bookmarks**. **+ → Manage bookmarks…** pins or
removes bookmarks. Open, Clone and Init are in the same menu. Removing a bookmark keeps all repository files on disk.
Bare repositories can be remote destinations; open working repositories in the UI.

For private repositories, configure your Git credential helper or SSH agent first.
Set up SSH host trust outside Logistics. The app uses stored credentials and avoids
invisible terminal prompts. Use URLs without passwords, HTTPS credentials, or query
tokens. Authentication errors appear in the operation log.

## Everyday changes

Choose **File status** in the left WORKSPACE section. It separates **Staged files**
and **Unstaged files**, with conflicts marked `!` in the unstaged list.
One file can appear in both staged and unstaged groups when you edit it after staging.
Select a file to inspect its diff; untracked text files show a bounded content preview.
Binary files show an explanation instead of text.

1. Check files or use **Stage file** beside the diff. **Stage all** includes untracked files and deletions.
2. Use **Unstage** to remove selected changes from the index while keeping working files.
3. Enter a commit subject and optional description, then **Commit**. The button is disabled until files are staged.
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
amending published history. Failed commits retain their message draft. Closing a repository tab or the app asks before discarding a draft.

Enable **Push changes immediately to origin/{branch}** to push after a successful
commit. This option requires an `origin` remote and an attached local branch.
If pushing fails, the commit remains saved; retry with **Push**.

The toolbar's **Commit** badge counts changed files, including untracked files.
**Pull** and **Push** count incoming and outgoing commits against the configured
upstream, using the last fetched remote state. **Fetch** updates that state and
has no numeric badge. Zero counts are hidden.

Each diff hunk has its own card. In File status, use **Stage Hunk** or **Unstage Hunk**
to change only that hunk's staging, or **Discard Hunk…** to discard an unstaged hunk
after confirmation. A changed preview must be refreshed before applying it.
Hunk actions require a complete, unfiltered patch for an ordinary tracked text
file; use file actions for untracked files, conflicts, renames, mode changes,
submodules and files with content conversion filters. History and Search cards
are read-only.

## History and branches

When files have pending changes, **Uncommitted changes** appears above the commit
history. Select it to review its files and diffs without leaving History. Use
File status for staging. It disappears after
the working tree and index become clean and the workspace refreshes.

Choose **History** in the left WORKSPACE section to see the commit graph, subjects, branch/tag decorations, authors,
dates, and hashes. Select a commit for its metadata and changed files below the graph;
select a changed file for its patch. Merge changed files compare the first parent.
Changed files are listed by full repository-relative path. **Search files by name
or path** filters this list independently of the history search. Below the list,
the commit message and identity fields summarize the selection; click a parent
hash to select and scroll to that commit in history. Diff hunks show old/new line
numbers and colored addition/deletion rows.
Patch headers are hidden in the normal view. Use the arrow buttons to jump between
hunks, **Wrap** to read long lines, and **Raw** to inspect the original patch.
**Ignore whitespace** hides whitespace-only differences for review; staging or
unstaging a file still affects all its changes. File badges identify added (+),
modified (M), deleted (−), renamed (→), untracked (?) and conflicted (!) files.
Use **Full tree at commit** to browse every historical file and read its contents.
Submodule entries show the recorded child commit. File actions stage, unstage or
discard whole files.

History starts with 200 commits. **Load 200 more commits** expands it up to 5,000.
History’s branch selector shows all loaded branches or only ancestors of the
current branch. Its quick filter matches loaded messages, authors, hashes and
refs, hiding the graph so omitted rows cannot imply false ancestry. **Search**
opens the separate repository-wide search view described below. **Find in preview**
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
- **Pull…** offers fast-forward only (initial default), merge, or rebase of the upstream.
- **Push…** pushes the current branch to its configured upstream. Alternatively,
  publish to a chosen remote/branch and set the upstream. Force-with-lease is available
  only after enabling it in Git preferences and confirming the individual push.

Ahead/behind counts reflect the last fetched local references. Fetch again to learn
about server changes. Push affects only the current branch and does not automatically
publish tags or other local branches. **Push tags with the selected branch** is
an opt-in Git preference.

## Git preferences

Use **More… → Git preferences…**, **+ → Git preferences…**, or repository
**Settings → Advanced → Git preferences…**. Before opening a repository, the
toolbar Settings button opens these preferences directly. Preferences apply
across retained repository panes and are saved in the feature's `git.json` file.
Cancel leaves preference edits unchanged.

- **General** controls the initial project folder, last-repository restoration,
  terminal choice (Terminal/iTerm on macOS), file-change refresh, optional periodic
  origin fetch, and staging/branch-switch confirmations. File watching is limited
  to 2,000 existing files/directories; use Refresh for larger repositories or
  changes in previously unwatched nested directories. Global author identity is
  edited only when its explicit checkbox is enabled; local identity overrides remain.
- **Accounts** adds, edits, removes and selects a default account per host. HTTPS
  tokens go directly through a secure credential helper: macOS Keychain, libsecret
  or Git Credential Manager with a native credential store. Tokens are sent on
  standard input, never saved in preferences or displayed in the operation log.
  Removing an account also erases its helper credential when you click OK.
  SSH accounts use existing keys and agents. GitHub browser sign-in opens Git
  Credential Manager in a terminal; install it first, finish its browser prompt,
  then add the username here and choose **Git Credential Manager** authentication.
  Logistics does not register its own OAuth application or request passwords.
- **Commit** controls selection (without staging), the default push checkbox,
  fixed-width message font and column guide, and an importable plain-text template.
  A nonempty Logistics template overrides an inherited Git template. Explicit
  repository templates, including “None”, take precedence. Existing drafts stay intact.
- **Diff** controls font, addition/deletion colors, wrapping, bounded text capture,
  and file patterns skipped for preview. Patterns affect review only. External
  diff/merge tool names use existing Git configuration; invoke them through More
  with a selected file/conflict. Binary files have no internal text preview.
- **Git** selects the executable, ignore list, default pull strategy, double-click
  staging, recursive submodule updates, dirty-submodule checks, tag pushing, HTTPS
  certificate verification, merge commit policy and history date source. These
  options affect Logistics commands without rewriting global Git configuration.
- **Custom Actions** supports ordered entries and optional shortcuts. Parameters
  are a JSON string array, such as `["status", "--short"]` for program `git`.
  `{repo}`, `{file}` and `{commit}` expand within individual arguments. A selected
  file/commit is required for its placeholder. Actions run in the repository,
  through the cancellable worker, without shell expansion.
- **Advanced** enables discard backups, persistent log visibility, force-with-lease,
  diagnostics, a GPG executable and per-host default HTTPS usernames. Backups keep
  the file bytes before whole-file or hunk discard under the repository's Git
  metadata in `logistics-backups/<id>/`, with `paths.json` mapping backup names to
  original paths. They are not committed. Restore them manually if needed.
- **Update** opens Logistics releases and release notes. Mercurial, embedded
  Git/git-flow/LFS runtimes, automatic update installation, Gravatars and language
  customization are not implemented here. Theme and language use Logistics itself.

Credential-store operations and explicitly enabled global identity changes are
separate from the JSON save; a failed save can leave those operations completed.
Review the operation error before retrying. Browser sign-in is a separate action
and is not undone by cancelling preferences. Hooks and custom actions manage
their own backups and side effects.

**More… → Create tag…** creates a lightweight tag or an annotated tag with a message,
at HEAD or the selected commit. Right-click a tag to view its commit, push it to a
chosen remote, or delete the local tag. Remote tags are kept when deleting locally.

## Stashes, conflicts, and recovery

**Stash…** saves changes with a message and optionally includes untracked files.
The stash context menu offers Apply, Pop, and Drop. Apply keeps the saved stash;
Pop removes it after a successful application. Review the confirmation before Drop.

A failed merge, pull/rebase, cherry-pick, or revert can leave conflicts. The workspace
refreshes and shows the current operation and conflict files. Double-click a conflicted
text file or choose **Resolve conflict…** to open the shared three-pane merge editor.
Apply independent changes, choose either side, keep both, or edit the center result
and mark the selected change resolved. Apply checks for external file/index changes.
Optionally check **Stage resolved file after saving**, then use **Continue**.
During rebase the side labels identify the rebased-onto revision and replayed commit.
Binary, delete/modify, symlink, submodule and conversion-filter conflicts require
manual resolution with Git or another appropriate editor.
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

This version has unified text diffs, side-by-side working/index comparisons, three-way text conflict resolution and whole-file staging. Hunk staging, interactive
rebase editing, reset/clean, merge-tool launching, LFS management, sparse/partial
cloning, worktree removal, and hosting-provider features are future additions.

**Compare sides…** beside a pending file opens full versions (Index / Working file, or HEAD / Index for staged files) in linked, resizable panes. This review does not stage or modify files.

## Repository settings and terminal

Use the toolbar’s **Settings** button for the current repository. **Commit
Template** selects inherited, disabled or custom starting text; an existing draft
is kept. **Remotes** stages additions, URL edits and removals until OK.
**Security** controls commit signing using your existing Git signing tools.
**Advanced** selects inherited or repository-specific author identity, opens
`.gitignore` in the enabled Text Editor, and offers the personal Git executable
chooser. Local settings are shared with linked worktrees; global Git settings
are kept. Cancel discards pending dialog changes.

The toolbar’s **Terminal** opens a terminal at the root of the active repository.
Open, Clone, Init and bookmark commands live in the repository tab’s **+** menu.

## Search repository history

Select **Search** in the Git sidebar. The search bar offers **Commit Message**
(including the message body), **Commit SHA** (a full hash or prefix of at least
four characters), **Branch** (commits reachable from matching local/remote
branches), **File Changes** (changed filename or path text, including deleted
paths), and **User** (author name or email). Text matches are case-insensitive.
**From** and **To** include both endpoint days, using local time and Git commit
timestamps. Search reads repository history rather than only the rows loaded
in History; results load in batches of 200, up to 5,000. Very large file-path
searches can reach the Git output limit; narrow the date range in that case.

Selecting a result shows its commit details, changed files and diff below the
results. In **History**, selecting **Uncommitted changes** stays in History and
shows the current files and their changes against HEAD, including both staged
and unstaged changes.
