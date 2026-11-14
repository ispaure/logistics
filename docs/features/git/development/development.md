# Git workspace

Requires Git 2.40+. See [authentication and usage](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).

## Try a diff preview change

On desktop, open a disposable Git repository. Commit a file, replace its contents with data containing a NUL byte, and select it in **File status**. Change the binary notice in `Python/features/git/diff_view.py:present_diff` and update the binary fixture. Run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/version_control/test_git_diff_view.py
```

Expect the new formatted notice and Git's exact original patch in **Raw**.

| Change | Owner under `Python/features/git/` |
| --- | --- |
| Workspace and shared diff preview | `ui/page.py` and `ui/repository_view.py` own the workspace. The repository view moves the same `ui/preview.py` widget between File status, History and Search. |
| File status, History and Search panels | `ui/layout.py` assembles the views built by `ui/changes.py`, `ui/history.py` and `ui/search.py`. |
| History, paging, graph | `ui/history_controller.py`, `graph.py` |
| Forms, capture, dispatch, execution | `ui/commands/forms.py`, `ui/commands/requests.py`, `ui/jobs.py`, `repository.py`, `runner.py` |
| Repository and application settings | `ui/settings.py`, `preferences.py`, `options.py`, `accounts.py` |

Capture repository and expected branch before modal input and recheck at dispatch and execution. One worker serializes jobs per pane. Refresh after failed writes and wait for worker retirement on close. Preserve draft vetoes.

The runner uses literal pathspecs, clears inherited repository location, suppresses terminal prompts and rejects embedded URL credentials. Keep credential-helper input on stdin and suppress its capture. Machine output fails above 8 MiB. Preview limits indicate truncation. Push uses the configured upstream refspec without automatic tag following. Force-with-lease requires opt-in and confirmation. A failed push leaves the commit.

History search uses bounded native Git queries and NUL-delimited paths. Commit file lists compare against the first parent.

Check complete current patches before hunk mutations. Merge saves atomically after checking for concurrent edits, then rechecks saved bytes and index stages before optional staging. Binary, delete/modify, symlink, submodule and conversion-filter conflicts require manual handling. Current-path editor opens route to the [IDE](../../ide/development/ide.md#implemented-contracts) or Text Editor.

Keep-backup discard verifies revisions, digests and flushed copies before publishing `paths.json`. Abort on cancellation or change. Checks are point-in-time. Repository config edits can partially apply and linked worktrees share config. Personal JSON detects concurrent writes and broadcasts the new baseline to retained panes. INI and JSON save separately. Reopen after a conflict. For focused tests under `Python/tests/version_control/`, use `test_git_backend.py`, `test_git_merge.py`, `test_git_commands.py` and `test_git_preferences.py`.
