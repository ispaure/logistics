"""Page selection for an rmdoc, independent of its edit/recovery checkpoint."""


def open_notebook_progress(book, root, *, resource=None, draft_path=None, app=None):
    from services.documents.progress import open_progress

    if resource is None and draft_path is None:
        return None, 0
    progress = open_progress(
        resource.provider if resource is not None else None,
        resource.path if resource is not None else draft_path,
        root, kind='notebook', revision=book.id, app=app,
        check=resource.check if resource is not None else None,
    )
    saved = progress.load()
    return progress, page_index(book, saved)


def page_index(book, saved):
    page_id = saved.get('page_id')
    for index, page in enumerate(book.pages):
        if page.id == page_id:
            return index
    index = saved.get('index')
    return min(max(index, 0), len(book.pages) - 1) if type(index) is int else 0


def page_location(editor):
    return dict(page_id=editor.notebook.pages[editor.index].id, index=editor.index)
