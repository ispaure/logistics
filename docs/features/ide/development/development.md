# Project IDE

Register a source directory to edit, search and navigate files in a desktop
project workspace. See the [user guide](../user/user.md) for controls and
[mobile availability](../user_mobile/user_mobile.md) for the platform boundary.

## Try a column guide change

On desktop, enable **IDE** in **Settings → Features** and select its rail
icon. Use **+ → Register / Open existing project** to register a temporary
directory containing a Python file. Open the file, use **Split right**, and
open **Project → Project Settings / Source Paths**. The **Column guide**
setting defaults to 120 for new projects and applies to both source views.

Try changing the default to 100 in `Python/features/ide/projects.py`
(`Project.column_guide` and the fallback in `Project.from_dict`). Keep explicit
saved values, including 0 for Off. `IDEPage.settings` in `ui/page.py` owns
the control, and `ProjectWorkspace` in `ui/workspace.py` applies it to existing
and new editors. Update the default assertions in `test_ide.py` and
`test_ide_markdown.py`. Run from the repository root after
[desktop setup](../../../development/getting-started.md):

```sh
python3 dev.py test desktop --exact-file Python/tests/ide/test_ide.py --exact-file Python/tests/ide/test_ide_markdown.py
```

Expect both files to pass. The tests check the fallback for older project
records, explicitly saved values, and updates in existing and split views
without modifying their text. Register a fresh disposable project after
relaunch to see the new default. An existing project with an explicitly
saved value keeps that value.

## Find the owner

Paths below are relative to `Python/features/ide/`.

| Change | Start here |
| --- | --- |
| Destination and project tabs | `__init__.py:register` declares the lazy `ide.workspace` page. `ui/page.py:IDEPage` manages projects, settings and retained tabs. |
| Project registration and workspace recovery | `projects.py:ProjectStore` owns the versioned checkpoint. `ui/workspace.py:ProjectWorkspace` owns worker lifetime, document groups and restoration. |
| Editing, split views or Markdown | `ui/documents.py` and `ui/markdown_document.py` own the project buffer and view adapters. |
| Project tree, rename or Git status | `ui/browser.py` wraps the shared lazy filesystem model. `ui/git_status.py` reads Git status independently of Git page activation or registration. |
| Search, definitions or usages | `ui/find_files.py` owns Find in Files. `analysis.py` and `ui/navigation.py` own the Jedi requests and navigation. `ui/usages.py` owns the result popup. |

See [IDE architecture and implementation](ide.md) for editing, navigation,
workspace recovery and test ownership. IDE and Text Editor share editor
primitives and change-marker services through commonUtils and
`Python/services/editors/ui/`. IDE owns project buffers and imports no
standalone Text Editor UI.

## Workspace checkpoint admission

`ProjectStore` keeps a version-1 `IDE/workspace.json` beside the application
preferences. It reads at most 4 MiB plus one byte and validates the entire
project list, identifiers and open-project selection before publishing any
state. Duplicate open IDs collapse and stale string IDs are filtered out.
Malformed or unsupported checkpoints leave an empty store with a visible
error and block writes over the original. Preserve that file for recovery.

Atomic publication checks the previous bytes to detect another instance's
writes. This is optimistic conflict detection. Reopen the workspace after
a write conflict before trying again. Project and file records remain
available when the root or file is temporarily inaccessible.

## Test ownership and execution

Select the file that owns your change in `Python/tests/ide/`. The
[architecture guide](ide.md#validation) maps the focused files to behavior.
The default full profile includes the 1,000-line theme-switch test and,
in the drag file, the extended side-drop matrix. The daily profile retains
both directions and both event receivers, merge/split, cancellation and
group-cap checks.

`test_ide_browser.py` needs native filesystem notifications even with offscreen
Qt. A restricted macOS sandbox can populate initial rows and miss later
creations. If automatic discovery times out, rerun that file with notification
access. Keep the real automatic-update assertion. The Git status tests
explicitly refresh after staging and retain an automatic timer-driven check
for a modified file becoming clean.

IDE registers a desktop Qt page. The mobile feature catalog and source
staging have no IDE entry or adapter.
