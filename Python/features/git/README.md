# Git workspace

An optional Logistics feature powered by the installed Git executable (2.40+).
See the [user guide](user_docs/index.md) for the interface and authentication setup.

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
- `ui/repository_view.py`: per-repository controls, snapshots, drafts, forms and previews.
- `ui/jobs.py`: sequential per-repository worker dispatch and shutdown.
- `ui/chrome.py`, `navigation.py`: scoped styling, vector toolbar icons and reference navigation.
- `ui/repository_tools.py`: worktree/submodule/subtree dialogs using that dispatcher.
- `ui/changes.py`, `history.py`, `preview.py`, `dialogs.py`: focused widgets.

The feature reuses commonUtils' dock-backed `Workspace`, Qt facade, painted sidebar icons, `CodeEdit`, and
platform process-group/cancellation helpers. Editing uses the optional existing
Text Editor service and the application's document host. Docking and tab reordering are shared with browser and document panes.

## Execution and lifecycle

One worker can run at a time per repository pane, covering both reads and writes.
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

Machine stdout and diagnostics are kept separate. Temporary files prevent pipe
deadlocks and excessive memory capture; stderr progress streams on POSIX and is
shown at completion on Windows. Machine responses are capped at 8 MiB and fail
explicitly on overflow. Text previews are capped at 1 MiB and show truncation.
The UI log is bounded by block/character counts and truncates oversized individual
lines before Qt text layout; URL redaction avoids unbounded regex backtracking.
Large output may still consume temporary disk space during command execution.

Git uses literal pathspecs and argument arrays, never shell command strings.
Inherited repository-location environment variables are cleared. Existing Git
configuration, hooks, signing, SSH commands, and credential helpers otherwise apply.
Terminal authentication prompts are disabled. HTTPS credentials/query tokens and
password-bearing URLs are rejected; diagnostics redact common credential forms.
There is no automatic retry of write operations.

Branch push uses an explicit `HEAD:<configured-upstream>` refspec and disables
automatic tag following, avoiding extra branches from `push.default=matching`.
Tag publishing is a separate action. No UI action performs a force push or reset.

## Navigation

The page sets `navigation_position=workspace` and `navigation_order=20`. The generic
sidebar places workspace contributions after Folder Hub and the contextual
documents/actions icons, before Tools. Active rclone sync jobs use Folder Actions,
so Git sits below that icon when it appears. A future Sync destination can use the
workspace position with order 10. Other feature destinations retain their location.

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
PYTHONPATH=Python:Python/tests QT_QPA_PLATFORM=offscreen python3 -m unittest \
  test_git_backend test_git_ui test_main_window test_feature_registry \
  test_feature_preferences test_settings_page
```

Tests use disposable repositories and local bare remotes, including rename/path
handling, empty repositories, clone/fetch/pull/push, conflict resolution and abort,
submodules, subtree add/pull/push, worktrees, reflog rescue, tags, and cancellation.
The submodule fixture opts into local file transport only for its test runner;
the application keeps Git's default transport rules. Optional subtree tests skip
when the installed Git lacks that extension. UI tests run offscreen and cover
worker ownership, shutdown retries, drafts, editor reuse, and sidebar ordering.

## Next increments

Hunk staging, interactive rebase editing, external merge-tool launching,
reset/clean previews, sparse/partial clones, LFS controls, graph refinement, and
hosting-provider integration remain separate follow-ups. Background remote fetch
and automatic filesystem polling are not enabled. Refresh on destination entry,
after operations, after integrated editor saves, or explicitly with Refresh.

## Shared diff and merge UI

Pending files offer **Compare sides…** using full text snapshots. Conflict files
open **Resolve conflict…** on double-click or from their context menu. The Git
adapter reads ancestor/local/incoming blobs from index stages, rejects truncated
or unsuitable inputs, and uses commonUtils' merge model/widget. Apply performs a
conflict-checked atomic save, optionally stages the result, and refreshes Git state.
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

`ui/application_settings.py` owns the General, Accounts, Commit, Diff, Git,
Mercurial status, Custom Actions, Update and Advanced pages.
`ui/application_preferences.py` applies changes to retained panes and connects
watching, periodic fetch, custom actions and external tools to the existing job
boundary. `options.py` validates the persisted schema and constructs command-scoped
Git defaults; only the explicit global-identity action writes global Git config.
`accounts.py` invokes approved native credential helpers directly, using sensitive
stdin with captured output suppressed, and delegates GitHub browser login to GCM.
Secrets are excluded from the account schema. Backend discard backups and submodule
checks remain in `repository.py`. The shared diff editor only adds a reusable
per-editor color override; application settings stay in this feature.
