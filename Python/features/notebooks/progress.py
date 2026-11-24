"""Page and brush preferences, independent of the notebook edit checkpoint."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from .brushes import BRUSHES, valid_intensity


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
    editor.eraser_kind = 'whole' if saved.get('eraser_kind') == 'whole' else 'partial'
    colors = saved.get('brush_colors')
    editor.brush_colors = {
        tool: color for tool, brush in BRUSHES.items()
        if type(color := colors.get(str(tool))) is int and color in brush['colors']
    } if isinstance(colors, dict) else {}
    intensities = saved.get('brush_intensities')
    editor.brush_intensities = {
        tool: intensity for tool in BRUSHES
        if valid_intensity(tool, intensity := intensities.get(str(tool)))
    } if isinstance(intensities, dict) else {}


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
    return dict(page_location(editor) if location is None else location,
                brush_colors=editor.brush_colors.copy(), brush_intensities=editor.brush_intensities.copy(),
                eraser_kind=editor.eraser_kind)
