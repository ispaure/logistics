# Project IDE

## Try a column guide change

On desktop, register a disposable Python project and split a source editor. Open **Project → Project Settings / Source Paths**. In `Python/features/ide/projects.py`, change `Project.column_guide` and the `from_dict` fallback from 120 to 100. Keep explicitly stored values, including 0 for Off. Update the default assertions and run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/ide/test_ide.py --exact-file Python/tests/ide/test_ide_markdown.py
```

Expect a 100-column default for fresh and older records without the setting. Explicit values survive and changes reach existing split views.

## Owners

Under `Python/features/ide/`, `ui/page.py` registers and retains projects. `projects.py` owns checkpoint admission. `ui/workspace.py` owns restore, editor groups and workers. See [architecture and validation](ide.md#validation), [user controls](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).

## Workspace checkpoint admission

`ProjectStore` validates the entire v1 `IDE/workspace.json` (4 MiB limit) before admitting state. Duplicate open IDs collapse and stale IDs are filtered. Missing paths retain their records. Malformed or unsupported data blocks writes. Preserve the original. Byte-checked atomic publication detects concurrent writers. Reopen after a conflict.

`test_ide_browser.py` requires native filesystem notifications even with offscreen Qt. Rerun with notification access if automatic discovery times out.
