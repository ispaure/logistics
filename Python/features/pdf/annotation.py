"""Create an editable, self-contained PDF-backed notebook beside its source."""
from pathlib import PurePosixPath

from features.notebooks.notebook import Notebook, MAX_ARCHIVE, MAX_PAGES
from services.documents.storage import DocumentResource
from .document import PDFDocument, MAX_PDF

LABEL = 'Duplicate as .rmdoc to annotate'


def notebook_from_pdf(data, name):
    pdf = PDFDocument(data)
    try:
        if pdf.count > MAX_PAGES:
            raise ValueError('PDF annotation supports at most 1,000 pages.')
        book = Notebook.new(name)
        for _ in range(pdf.count - 1):
            book.add_page()
        book.content.update(fileType='pdf', originalPageCount=pdf.count)
        book.members[book.id + '.pdf'] = data
        for index, page in enumerate(book.pages):
            page.record['redir'] = dict(value=index)
        return book
    finally:
        pdf.close()


def duplicate_pdf(provider, path, *, cancelled=lambda: False):
    """Provider publication with revision=None refuses existing destinations."""
    source = PurePosixPath(provider.relative(path))
    if source.suffix.lower() != '.pdf':
        raise ValueError('Choose a PDF to duplicate as a notebook.')
    destination = str(source.with_suffix('.rmdoc'))
    try:
        provider.entry(destination)
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError('A file already exists at ' + destination + '. Rename it before duplicating this PDF.')
    with DocumentResource(provider, str(source), max_bytes=MAX_PDF) as resource:
        data = resource.read(cancelled=cancelled)
        book = notebook_from_pdf(data, source.stem)
        if resource.check()['revision'] != resource.revision:
            raise ValueError('The PDF changed while converting; reopen it and try again.')
        DocumentResource.publish(provider, destination, book.to_bytes(), max_bytes=MAX_ARCHIVE,
                                 validate=Notebook.read, cancelled=cancelled)
    return destination
