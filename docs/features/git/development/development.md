# Git workspace

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

An optional Logistics feature powered by the installed Git executable (2.40+).
See the [user guide](../user/user.md) for the interface and authentication setup.

## Ownership

- `__init__.py`: lazy unified `Feature`/`PageContribution` declaration.
- `runner.py`: shell-free, binary-safe command execution, capability check,
  cancellation, timeout, capture limits, and diagnostic redaction.
- `models.py`: porcelain-v2 status, NUL-delimited history/ref/tree models.
- `repository.py`: Qt-independent queries, snapshots, and Git operations.
- `preferences.py`: atomic per-user repository bookmarks, executable selection,
  last repository, and subtree mappings in `git.json` beside Logistics preferences.
- `graph.py`: lane geometry for a bounded, topologically ordered commit DAG.
- `ui/worker.py`: retained cancellable Qt worker; no widgets accessed from its thread.
- `ui/page.py`: shared dock-backed workspace and retained repository-pane lookup.
- `ui/repository_view.py`: per-repository controls, snapshots, drafts, command forms and host lifecycle.
- `ui/history_controller.py`: composed history/search/preview orchestration; owns
  history limits, preview reload selection and deferred search/focus state.
- `ui/menus.py`: conventional menus sharing existing actions and selection/busy guards.
- `ui/jobs.py`: sequential per-repository worker dispatch and shutdown.
- `ui/chrome.py`, `navigation.py`: scoped styling, vector toolbar icons and reference navigation.
- `ui/repository_tools.py`: worktree/submodule/subtree dialogs using that dispatcher.
- `ui/changes.py`, `history.py`, `preview.py`, `dialogs.py`: focused widgets.

The feature reuses commonUtils' dock-backed `Workspace`, Qt facade, painted sidebar icons, `CodeEdit`, and
platform process-group/cancellation helpers. Editing uses the enabled
IDE through an application callback for registered projects, with the Text Editor
service and document host as fallback. Docking and tab reordering are shared with browser and document panes.

## Execution and lifecycle

One worker can run at a time per repository pane, covering both reads and writes.
`RepositoryHistory` submits reads through that same job owner; it creates no
worker and cannot run a second operation. Existing view callbacks/state accessors
delegate to the controller so menu/widget connections retain their entry points.
Commit previews, working-file comparisons, parent/tag navigation and search all
use captured repository paths. Search results also validate their query/limit
snapshot before publication. Mutation commands remain with the repository view
and backend, including hunk actions and conflict operations.
Different repositories can work independently; opening an already-retained repository
reveals its existing pane. Switching tabs preserves its draft, preview and log.
Every worker gets a fresh runner, a cancellation event, and a captured repository
path. Repository selection and mutation controls stay disabled until completion.
Refresh requests made while busy are coalesced. Writes refresh even on failure
or cancellation: an unsuccessful merge can still create a valid conflict state.

The main window connects contributed pages' `idle` signals to deferred closing.
`prepare_close()` requests cancellation and returns false until the worker ends;
the thread remains owned until Qt's `finished` signal arrives. No thread is forcibly
terminated. Commit-message drafts can veto closing a repository tab or the application.

`RepositoryView._render` admits the snapshot before projecting controls. Named
helpers render repository/branch identity, action badges and retained changed-file
preview selection. History/navigation, operation state and busy publication retain
their existing order in `_render`; preview restoration follows those controls and
keeps its selection signal blocker. The helpers issue no Git queries and add no
state owner. Worker sequencing, refresh coalescing, draft vetoes, mutation commands
and repository-path capture remain in the existing view/job/backend owners.

Machine stdout and diagnostics are kept separate. Temporary files prevent pipe
deadlocks and excessive memory capture; stderr progress streams on POSIX and is
shown at completion on Windows. Machine responses are capped at 8 MiB and fail
explicitly on overflow. Text previews default to 1 MiB and show truncation; the personal Diff preference
allows 16–16,384 KiB. The runner receives that limit per job.
The UI log is bounded by block/character counts and truncates oversized individual
lines before Qt text layout; URL redaction avoids unbounded regex backtracking.
Large output may still consume temporary disk space during command execution.

`GitRunner.run()` keeps admission, captured execution, exception translation and
result validation together. Two private helpers in `runner.py` prepare executable/
argument arrays and the child environment. Preparation still precedes input-size
validation, preserving existing failure order. Helpers use the current runner
options for each call; they neither cache policy nor start processes.

Git uses literal pathspecs and argument arrays, never shell command strings.
Inherited repository-location environment variables are cleared. Existing Git
configuration, hooks, signing, SSH commands, and credential helpers otherwise apply.
Terminal authentication prompts are disabled. HTTPS credentials/query tokens and
password-bearing URLs are rejected; diagnostics redact common credential forms.
There is no automatic retry of write operations.

Branch push uses an explicit `HEAD:<configured-upstream>` refspec and disables
automatic tag following, avoiding extra branches from `push.default=matching`.
Tag publishing is separate unless the user opts into pushing tags with a branch.
Force-with-lease requires a personal preference and per-push confirmation; the UI
does not expose reset/clean.

## Navigation

The declaration contributes `git.workspace` with the `git` navigation icon.
The shell places the page using its contribution and page navigation properties;
feature code does not insert controls into the rail. Workspace actions independently
hosts rclone jobs. Keep exact ordering in the shell rather than treating a proposed
future destination as part of this feature's contract.

## Workspace layout

Open repositories have reorderable, detachable tabs. Each retained pane owns its
toolbar, including Commit/Pull/Push/Fetch/Branch, remote/folder/terminal actions and
settings. Real toolbar actions remain accessible through Qt's overflow menu in
narrow or floating panes. Open, Clone, Init and bookmarks are available from the repository tab’s **+** menu. A reference tree
provides File status, History and Search, hierarchical branches/remotes, tags,
stashes, configured submodules and saved subtrees. File status uses two separately
resizable lists, a shared diff preview and a bottom commit composer. History puts
the graph above a files/metadata pane and the preview. The same CodeEdit preview
moves between hosts, keeping a single selection/search implementation. Content uses
a font one point smaller than the host; the toolbar retains the host font. Compact
row spacing follows Qt font metrics, and controls inherit the application theme.
Changed files appear as flat repository-relative paths with their own filename
filter. Commit metadata shows the message and linked parent hashes; following a
parent focuses it in history, loading additional history when necessary (up to
5,000 commits). The local CodeEdit subclass adds old/new line numbers and visible
hunk/addition/deletion bands, while keeping ordinary blob previews unchanged.
`diff_view.py` presents unified patches independently of Qt. The preview hides
patch headers by default, displays separate hunk cards, and supplies hunk navigation, wrapping, whitespace-only
filtering, and an explicit raw view. Status badges combine color with symbols;
graph lanes use Okabe–Ito hues and filled commit dots.

Commit file lists use NUL-delimited first-parent comparisons, including root
commits and deletions; full historical trees remain available separately. File
staging checkboxes dispatch through the same serialized command boundary.
Hunk actions verify the current patch and use Git's checked patch application
to stage, unstage or discard one complete hunk. Special file changes use whole-file
actions. The commit composer can push a successful commit to `origin` on the
current branch; a failed push preserves that commit. Toolbar badges show changed
files and upstream ahead/behind counts from the latest fetched state.

## Validation

From the repository root:

```sh
PYTHONPATH=Python:. QT_QPA_PLATFORM=offscreen python3 -m unittest \
  tests.version_control.test_git_backend tests.version_control.test_git_ui \
  tests.application.test_main_window tests.application.test_feature_registry \
  tests.application.test_feature_preferences tests.application.test_settings_page
```

Tests use disposable repositories and local bare remotes, including rename/path
handling, empty repositories, clone/fetch/pull/push, conflict resolution and abort,
submodules, subtree add/pull/push, worktrees, reflog rescue, tags, and cancellation.
The submodule fixture opts into local file transport only for its test runner;
the application keeps Git's default transport rules. Optional subtree tests skip
when the installed Git lacks that extension. UI tests run offscreen and cover
worker ownership, shutdown retries, drafts, editor reuse, and sidebar ordering.

## Next increments

Interactive rebase editing, reset/clean previews, sparse/partial clones and LFS
controls remain separate work. Personal preferences already enable bounded file
watching, periodic origin fetch, custom actions and external diff/merge tools.
Refresh also runs on destination entry, after operations and integrated editor saves,
or explicitly with Refresh.

## Shared diff and merge UI

Pending files offer **Compare sides…** using full text snapshots. Conflict files
open **Resolve conflict…** on double-click or from their context menu. The Git
adapter reads ancestor/local/incoming blobs from index stages, rejects truncated
or unsuitable inputs, and uses commonUtils' merge model/widget. Apply performs a
conflict-checked atomic save, optionally stages the result, and refreshes Git state.
Before optional staging, the adapter rechecks index entries and reads at most the
expected saved byte count plus one. A changed or enlarged file remains unstaged;
its contents are preserved for review instead of being read without a bound.
Binary, delete/modify, symlink, submodule and conversion-filter conflicts retain
manual handling. `preview.py` imports its shared renderer from
`commonUtils.ui.code_editor.diff_bands`; Git patch parsing stays in `diff_view.py`.

## Repository settings

The toolbar’s Settings button opens settings for the active repository: commit
template, remotes, signing and author identity. Changes are staged in the dialog
and written through the pane’s existing Git worker when OK is clicked. Cancel
keeps Git configuration unchanged. Linked worktrees share local configuration;
inherited/global settings are never rewritten. Repository changes are not a
transaction: if a Git command fails, earlier successful changes may remain; the
operation log reports the error and the pane refreshes.

Custom templates are stored in Git metadata, outside tracked files, and populate
an empty commit composer. Existing drafts are kept. Signing uses existing Git
keys and tools; Logistics does not create keys or manage signing agents.
Advanced also exposes the repository’s `.gitignore` editor and the separate
personal Git executable setting. Automatic background fetch, custom message
replacements and other application-specific preferences from third-party Git
clients are not implemented by this dialog.

Terminal opens at the current repository root. Toolbar artwork is painted at
1×, 2×, 3× and 4× resolution so Retina displays do not enlarge low-resolution
bitmaps. Repository settings UI lives in `ui/settings.py`; command behavior
stays in `repository.py`, with worker ownership in `ui/jobs.py`.

## History search

`ui/search.py` owns a dedicated Search view with field and date controls, reusing
the history file/metadata widgets. `Repository.search_history()` performs native
Git searches across reachable history, with bounded output and result paging.
File-path searches parse NUL-separated names, preserving unusual filenames.
Queries use the existing serialized/cancellable pane worker; changes during a
job queue a new search and stale results are discarded.

Uncommitted changes stay in History and use its existing lower file/diff panes.
Their previews compare tracked working files to HEAD; untracked files and
unborn repositories use the bounded file preview.

## Application preferences

`ui/application_settings.py` contributes an embedded panel to Logistics feature
settings, with standard tabs for General, Accounts, Commit, Diff, Git,
Mercurial status, Custom Actions, Update and Advanced pages.
`ui/application_preferences.py` applies changes to retained panes and connects
watching, periodic fetch, custom actions and external tools to the existing job
boundary. `options.py` validates the persisted schema and constructs command-scoped
Git defaults; only the explicit global-identity action writes global Git config.
Commands disable Git's optional index writes so background status reads do not
trigger another filesystem-watcher refresh. Required mutation locks remain enabled.
`accounts.py` invokes approved native credential helpers directly, using sensitive
stdin with captured output suppressed, and delegates GitHub browser login to GCM.
Secrets are excluded from the account schema. Backend discard backups and submodule
checks remain in `repository.py`. The shared diff editor only adds a reusable
per-editor color override; application settings stay in this feature.

## Persistence and editor adapter

Preferences serialize the existing indented JSON payload and use shared atomic
byte publication. Sparse INI settings, legacy custom-path fields and malformed
file protection remain feature-owned. Git, IDE and Text Editor use the neutral
`services/editors/ui/fonts.py` adapter for custom preference paths; default font
coordination remains shared styling.

## Captured command boundary

`ui.commands.forms.RepositoryCommands` collects form/menu inputs and dispatches
through the pane's existing serialized `GitJobs` worker. `ui.commands.requests.GitCommand`
freezes repository path, backend method, arguments/options and any expected branch.
`repository.py` keeps Git behavior; `ui/repository_view.py` keeps presentation,
refresh and retained worker lifetime. Do not add a second mutation queue.

Capture repository/branch before opening a modal form or context menu. Dispatch
rejects a changed/closing view, and request execution rechecks the actual repository
path and any captured branch on the worker before invoking the backend. Branch-
sensitive operations include commit, push/pull, merge/revert/cherry-pick, switch,
stash, staging/hunk/conflict actions and selected branch/tag creation. Other
operations still retain captured repository identity. These checks do not freeze
HEAD/index/worktree contents; backend conflict and checked-patch validation remain
necessary.

UI completion callbacks apply only to the still-current repository. Existing Git
preferences, confirmations, credential handling and no-automatic-retry policy
remain unchanged. `test_git_commands` covers captured context and stale execution;
Git UI/backend tests cover forms, stash/index behavior and worker retirement.

## Command capture ownership

`runner.GitRunner` retains Git options, repository environment filtering, input
limits, credentials policy, version requirements and error translation. Its shared
capture backend spools stdout/stderr separately, preserving binary stdout, stderr
progress/tail, timeout/cancellation and completion-before-truncation behavior.
Sensitive requests discard both outputs. Diagnostic redaction is best effort;
Git does not use it as a substitute for discarding sensitive output.

The capture helper supervises stdin independently, so a child which stops reading
cannot hold up deadline or cancellation checks. Credential input remains in a pipe;
it is not added to disk spools. Writer retirement, early child pipe closure and
callback failure are covered by shared tests, with Git consumers retaining their
existing input-size and sensitive-output policy.

## Verified discard backups

When **Keep backups** is enabled, `Repository.backup_files` captures each selected
file's revision and SHA-256, copies and flushes the private backup, and verifies
its content before allowing whole-file or hunk discard. It checks every selected
path again before publishing the existing `paths.json` mapping, including files
that were initially absent. An observed external edit, new file, corrupt copy or
cancellation aborts discard. Existing backups are retained in Git metadata.
This preparation does not lock out other editors; Git still owns the subsequent
mutation and a concurrent change after the final check remains possible.
`test_git_backend.py` covers corrupt copies and changes during multi-file backup;
`test_git_preferences.py` covers the actual enabled UI and backup mapping.

## Settings writer conflicts

Git JSON preferences retain the bytes loaded by each instance. Save checks that
baseline before separate INI changes and during atomic JSON publication, rejecting
stale edits, external deletion and a file created after a missing-file load. A
successful write advances the baseline to the published bytes. Settings fanout
uses the preference owner's `adopt_saved` method to copy fields and the matching
baseline together, so retained views remain writable after in-process updates.

INI and JSON writes remain separate operations; this is optimistic conflict
detection, not a multi-file transaction or cross-process writer lock. The error
asks the user to reopen the workspace rather than overwrite another instance.
`test_git_preferences.py` covers competing instances and retained-view fanout.
