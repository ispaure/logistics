"""Desktop notebook host selection; the notebook editor receives only storage."""
from pathlib import Path
from services.documents.storage import DocumentResource
from commonUtils.ui.resources.picker import ResourceTaskDialog
from commonUtils.ui import pyside as qt


def open_notebook_choice(choice, parent=None, *, create=False):
    from features.notebooks.notebook import Notebook, MAX_ARCHIVE
    from features.notebooks.storage import NotebookDocument
    from features.notebooks.ui.workspace import open_workspace
    dialog = ResourceTaskDialog(parent, 'Creating notebook' if create else 'Opening notebook')
    opened = []
    def work(report, cancelled):
        resource = DocumentResource(choice.provider, choice.path, max_bytes=MAX_ARCHIVE)
        try:
            if create:
                DocumentResource.publish(choice.provider, choice.path, Notebook.new(Path(choice.path).stem).to_bytes(),
                    max_bytes=MAX_ARCHIVE, validate=Notebook.read, cancelled=cancelled)
            book = Notebook.read(resource.read(cancelled=cancelled))
            return NotebookDocument(book, resource=resource)
        except Exception:
            resource.close()
            raise
    def completed(document, error):
        try:
            if error:
                qt.QMessageBox.warning(parent, 'Notebook', error)
            elif dialog.operation.cancelled.is_set():
                document.close()
            else:
                window = open_workspace(parent, document=document)
                opened.append(window)
        except Exception as failure:
            if document is not None:
                document.close()
            qt.QMessageBox.warning(parent, 'Notebook', str(failure))
        finally:
            choice.close()
            dialog.accept()
            dialog.deleteLater()
    dialog.operation.completed.connect(completed)
    dialog.operation.start(work, message='Preparing notebook…')
    dialog.exec()
    return opened[0] if opened else None


def new_notebook_document(parent=None):
    from features.notebooks.notebook import Notebook
    from features.notebooks.storage import NotebookDocument
    from features.notebooks.ui.workspace import open_workspace
    return open_workspace(parent, document=NotebookDocument(Notebook.new()))


def choose_notebook_document(parent=None):
    from services.documents.ui.editors import choose_editor_resource
    choice = choose_editor_resource(parent, 'open', extensions=('.rmdoc',))
    if choice is not None:
        return open_notebook_choice(choice, parent)
