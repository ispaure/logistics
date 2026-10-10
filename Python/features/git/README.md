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
- `ui/page.py`: workspace state, forms, and sequential job dispatch.
- `ui/chrome.py`, `navigation.py`: scoped styling, vector toolbar icons and reference navigation.
- `ui/repository_tools.py`: worktree/submodule/subtree dialogs using that dispatcher.
- `ui/changes.py`, `history.py`, `preview.py`, `dialogs.py`: focused widgets.

The feature reuses commonUtils' Qt facade, painted sidebar icons, `CodeEdit`, and
platform process-group/cancellation helpers. Editing uses the optional existing
Text Editor service and the application's document host. commonUtils is unchanged.

## Execution and lifecycle

One worker can run at a time in a workspace, covering both reads and writes.
Every worker gets a fresh runner, a cancellation event, and a captured repository
path. Repository selection and mutation controls stay disabled until completion.
Refresh requests made while busy are coalesced. Writes refresh even on failure
or cancellation: an unsuccessful merge can still create a valid conflict state.

The main window connects contributed pages' `idle` signals to deferred closing.
`prepare_close()` requests cancellation and returns false until the worker ends;
the thread remains owned until Qt's `finished` signal arrives. No thread is forcibly
terminated. Commit-message drafts can veto closing or repository switching.

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

Repository bookmarks appear as tabs beneath an icon toolbar. A reference tree
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
patch headers by default and supplies hunk navigation, wrapping, whitespace-only
filtering, and an explicit raw view. Status badges combine color with symbols;
graph lanes use Okabe–Ito hues and filled commit dots.

Commit file lists use NUL-delimited first-parent comparisons, including root
commits and deletions; full historical trees remain available separately. File
staging checkboxes dispatch through the same serialized command boundary.

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

Hunk staging, side-by-side diffs, interactive rebase, external merge-tool launching,
reset/clean previews, sparse/partial clones, LFS controls, graph refinement, and
hosting-provider integration remain separate follow-ups. Background remote fetch
and automatic filesystem polling are not enabled. Refresh on destination entry,
after operations, after integrated editor saves, or explicitly with Refresh.
