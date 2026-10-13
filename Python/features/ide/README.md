# Project IDE

[User guide](user_docs/README.md) · [Architecture](../../../docs/developer/ide.md)

`projects.py` owns the versioned registration store. `page.py` manages project
settings and retained tabs. `workspace.py` owns canonical document paths, groups,
workers, close decisions and restoration. `browser.py` wraps the shared lazy
filesystem model. `documents.py` owns shared text buffers and independent CodeEdit views;
`navigation.py` presents `analysis.py`'s background Jedi and bounded scan results.
No IDE import depends on the standalone Text Editor. `git_status.py` optionally
uses the Git backend for read-only project-tree colors independently of Git UI
activation or repository registration.

Project containers reuse shared Workspace sizing, detachment and menu routing.
Internal editor gestures use ScopedTabBar, confined to each project’s editor
splitter; file tabs never become floating windows. See the user guide for menus
and left/center/right snapping.
