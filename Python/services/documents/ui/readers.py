"""Shared Local/LocalCrypt picker and provider-owned reader presentation."""
from contextlib import nullcontext
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.resource_picker import ResourceTaskDialog
from services.documents.ui.editors import choose_editor_resource, retain


def choose_reader_document(parent, kind, *, current=None, open_local=None):
    source = getattr(current, 'source', None)
    if current is not None and source is None:
        from commonUtils.runtime.local_files import LocalFiles
        source = LocalFiles(Path(current.path).anchor)
    directory = source.relative(current.path.parent) if current is not None else None
    choice = choose_editor_resource(parent, 'open', source, directory=directory,
        extensions=('.epub',) if kind == 'epub' else ('.cbz',))
    if choice is None:
        return None
    if not getattr(choice.provider, 'private', False):
        path = choice.provider.root / choice.path
        choice.close()
        if open_local is not None:
            return open_local(path)
        if kind == 'epub':
            from features.books.ui.controller import BooksController
            owner = getattr(parent, 'document_service_owner', parent)
            controller = getattr(owner, '_books_controller', None)
            if controller is None:
                controller = owner._books_controller = BooksController(owner)
            return controller.open(path)
        from features.comics.reader import open_reader
        return open_reader(path)
    return open_reader_choice(choice, parent, kind)


def open_reader_choice(choice, parent, kind, *, password=None):
    """Retain the selected provider until loading or the resulting reader retires."""
    path = choice.provider.root / choice.path
    dialog = ResourceTaskDialog(parent, 'Opening private document')
    operation = dialog.operation
    opened = []
    def read(report, cancelled):
        scope = getattr(choice.provider, 'operation', None)
        with scope(cancelled) if scope else nullcontext():
            if kind == 'epub':
                from features.books.epub import EPUBBook
                return EPUBBook(path, source=choice.provider, password=password)
            from features.comics.library import ComicDocument
            from features.comics.pages import ComicPages
            return ComicPages(path, ComicDocument(path, source=choice.provider, password=password))
    def done(document, error):
        transferred = False
        window = None
        try:
            owner = getattr(parent, 'document_service_owner', None)
            if operation.cancelled.is_set() or getattr(owner, 'closing', False):
                return
            if error:
                from services.documents.zip_passwords import is_password_error
                if is_password_error(error):
                    from ui_new.dialogs.archive_password import ask_password
                    retry = ask_password(path, error, parent, source=choice.provider)
                    if retry is not None:
                        window = open_reader_choice(choice, parent, kind, password=retry)
                        if window is not None:
                            opened.append(window)
                        transferred = True
                else:
                    if getattr(choice.provider, 'remote_storage', False):
                        from features.rclone.remote_policy import LOCAL_COPY_MESSAGE
                        error = error + '\n\n' + LOCAL_COPY_MESSAGE
                    qt.QMessageBox.warning(parent, 'Open', error)
                return
            if kind == 'epub':
                from features.books.ui.reader import BookWindow
                window = BookWindow(document)
                from services.documents.ui.private_views import protect_private_view
                protect_private_view(window, choice.provider)
                window.destroyed.connect(lambda: choice.close())
                retain(window)
                transferred = True
                opened.append(window)
            else:
                from features.comics.reader import open_reader
                window = open_reader(document)
                from services.documents.ui.private_views import protect_private_view
                protect_private_view(window, choice.provider)
                opened.append(window)
                if window.pages is document:
                    window.destroyed.connect(lambda: choice.close())
                    transferred = True
        except Exception as error:
            if window is not None and not transferred:
                window.close()
            qt.QMessageBox.warning(parent, 'Open', str(error))
        finally:
            if not transferred:
                choice.close()
            dialog.accept()
            dialog.deleteLater()
            if getattr(parent, 'closing', False) or getattr(getattr(parent, 'document_service_owner', None), 'closing', False):
                from commonUtils.ui.document_host import close_document
                close_document(parent)
            elif hasattr(parent, 'idle'):
                parent.idle.emit()
    operation.completed.connect(done)
    operation.start(read, message='Opening private document…')
    dialog.exec()
    return opened[0] if opened else None
