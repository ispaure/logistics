"""Desktop annotation command using the existing document operation dialog."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.resources.picker import ResourceTaskDialog
from features.pdf.annotation import duplicate_pdf, LABEL


def annotate_pdf(provider, path, parent=None, *, refresh=lambda: None):
    dialog = ResourceTaskDialog(parent, LABEL)
    result = []

    def work(report, cancelled):
        return duplicate_pdf(provider, path, cancelled=cancelled)

    def done(destination, error):
        try:
            if error:
                qt.QMessageBox.warning(parent, LABEL, error)
            elif not dialog.operation.cancelled.is_set():
                from services.documents.storage import DocumentResource
                from features.notebooks.notebook import Notebook, MAX_ARCHIVE
                from features.notebooks.storage import NotebookDocument
                from features.notebooks.ui.workspace import open_workspace
                resource = DocumentResource(provider, destination, max_bytes=MAX_ARCHIVE)
                try:
                    document = NotebookDocument(Notebook.read(resource.read()), resource=resource)
                    result.append(open_workspace(parent, document=document))
                except Exception:
                    resource.close()
                    raise
                refresh()
        except Exception as failure:
            qt.QMessageBox.warning(parent, LABEL, str(failure))
        finally:
            dialog.accept()
            dialog.deleteLater()

    dialog.operation.completed.connect(done)
    dialog.operation.start(work, message='Creating notebook beside the PDF…')
    dialog.exec()
    return result[0] if result else None


def annotation_actions(selected, context):
    from commonUtils.filesystem import BrowserAction
    if len(context.selection) != 1:
        return ()
    path = Path(context.selection[0].path)
    if path.suffix.lower() != '.pdf' or not path.is_file():
        return ()

    def run(ctx):
        from services.documents.storage import local_document_resource
        from features.pdf.document import MAX_PDF
        with local_document_resource(path, max_bytes=MAX_PDF) as resource:
            return annotate_pdf(resource.provider, resource.path, ctx.widget.window(), refresh=ctx.browser.refresh)

    return (BrowserAction('pdf.annotate', LABEL, run, source='PDF', category='open', order=30),)
