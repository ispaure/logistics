"""Page and brush preferences, independent of the notebook edit checkpoint."""

from .brushes import BRUSHES


def open_notebook_progress(book, root, *, resource=None, draft_path=None, app=None):
    from services.documents.progress import open_progress

    if resource is None and draft_path is None:
        return None, {}
    progress = open_progress(
        resource.provider if resource is not None else None,
        resource.path if resource is not None else draft_path,
        root, kind='notebook', revision=book.id, app=app,
        check=resource.check if resource is not None else None,
    )
    return progress, progress.load()


def restore_notebook_progress(editor, saved):
    editor.index = page_index(editor.notebook, saved)
    colors = saved.get('brush_colors')
    editor.brush_colors = {
        tool: color for tool, brush in BRUSHES.items()
        if type(color := colors.get(str(tool))) is int and color in brush['colors']
    } if isinstance(colors, dict) else {}


def page_index(book, saved):
    page_id = saved.get('page_id')
    for index, page in enumerate(book.pages):
        if page.id == page_id:
            return index
    index = saved.get('index')
    return min(max(index, 0), len(book.pages) - 1) if type(index) is int else 0


def page_location(editor):
    return dict(page_id=editor.notebook.pages[editor.index].id, index=editor.index)


def notebook_progress_state(editor, location=None):
    return dict(page_location(editor) if location is None else location, brush_colors=editor.brush_colors.copy())
