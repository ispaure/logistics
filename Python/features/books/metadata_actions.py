"""One browser verb dispatches to EPUB and ComicInfo editors by selected type."""
from .file_type import EPUBFile


def edit_metadata(context):
    from .controller import BooksController
    epubs = [item.path for item in context.selection if isinstance(item, EPUBFile)]
    comics = [item.path for item in context.selection if not isinstance(item, EPUBFile)]
    controller = context.controller
    results = []
    if epubs:
        if isinstance(controller, BooksController):
            books = controller
        else:
            books = getattr(controller, '_books_metadata_controller', None)
            if books is None:
                books = BooksController(context.host)
                controller._books_metadata_controller = books
                books.idle.connect(controller._notify_idle)
        results.extend(books.open(path, edit=True) for path in epubs)
    if comics:
        if not hasattr(controller, '_open_editor'):
            # Reuse the host's existing comic controller, including its password,
            # batch edit and lifetime handling; no second comic editor service.
            from features.registry import get_feature_definition
            controller = get_feature_definition('comics').install_browser(context.browser, host=context.host).controller
        results.append(controller._open_editor(tuple(comics)))
    return results
