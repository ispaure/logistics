"""Lazy IDE metadata and GUI-thread snapshots for LM project context."""
from commonUtils.ui import pyside as qt
from ..project_tools import MAX_FILE_BYTES


def ide_pages(owner):
    from features.ide.page import IDEPage
    pages = [widget for widget in qt.QApplication.allWidgets() if isinstance(widget, IDEPage)]
    return sorted(pages, key=lambda page: page.window() is not owner.window())


def registered_projects(owner):
    pages = ide_pages(owner)
    if pages:
        projects = {}
        for page in pages:
            for key, project in page.store.projects.items():
                projects.setdefault(key, project)
        return projects
    from features.ide.projects import ProjectStore
    store = ProjectStore()
    if store.error:
        raise ValueError(store.error)
    return store.projects


def editor_context(owner, project):
    """Copy text on GUI thread; workers receive plain strings, never Qt objects."""
    buffers, selections = {}, []
    total = 0
    for page in ide_pages(owner):
        for workspace in page.views:
            if workspace.project.id != project.id:
                continue
            for path, document in workspace.documents.items():
                try:
                    relative = path.resolve().relative_to(project.root).as_posix()
                except ValueError:
                    continue
                text = document.toPlainText()
                if len(text.encode('utf-8')) > MAX_FILE_BYTES:
                    continue
                if relative not in buffers:
                    total += len(text.encode('utf-8'))
                    if total > 4 * 1024 * 1024:
                        raise ValueError('Open editor context exceeds 4 MiB. Close some files before using Code mode.')
                    buffers[relative] = text
                editor = getattr(document, 'editor', document)
                cursor = editor.textCursor()
                if cursor.hasSelection():
                    line = editor.document().findBlock(cursor.selectionStart()).blockNumber() + 1
                    selections.append((relative, line, cursor.selectedText().replace('\u2029', '\n')))
    return buffers, list(dict.fromkeys(selections))
