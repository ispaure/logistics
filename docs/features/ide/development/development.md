# Project IDE

The desktop IDE opens source files within registered projects. The project
record supplies folder exclusions and editor settings. Split editors share
the same buffer, so a project setting such as the column guide needs to
reach each view of that document.

## Follow a project setting

Open **Project → Project Settings…** in a disposable project.
`Python/features/ide/projects.py:Project` owns persisted values such as the
column guide and their defaults for older records. The fixture suites check
explicit values, disabled guides and updates to split views. The Markdown
tests cover the related shared-document lifecycle.

```sh
python3 dev.py test desktop --exact-file Python/tests/ide/test_ide.py --exact-file Python/tests/ide/test_ide_markdown.py
```

## Owners

Under `Python/features/ide/`, `ui/page.py` registers and retains projects. `projects.py` owns checkpoint admission. `ui/workspace.py` owns restore, editor groups and workers. See [architecture and validation](ide.md#validation), [user controls](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).

`ui/project_settings.py` shares a staged configuration dialog between project
registration and the Project menu. `ui/project_structure.py` keeps excluded
folders visible for editing. `ui/project_interpreter.py` loads the local
package inventory on request and retires its probe on close.

## Workspace checkpoint admission

`ProjectStore` validates the entire v1 `IDE/workspace.json` (4 MiB limit) before admitting state. Duplicate open IDs collapse and stale IDs are filtered. Missing paths retain their records. Malformed or unsupported data blocks writes. Preserve the original. Byte-checked atomic publication detects concurrent writers. Reopen after a conflict.

`test_ide_browser.py` requires native filesystem notifications even with offscreen Qt. Rerun with notification access if automatic discovery times out.
