"""PDF reading on desktop and mobile."""
FEATURE_DESCRIPTION = 'Read and search PDFs with page-number navigation and vertical swipes.'


def launch(parent):
    from services.documents.ui.readers import choose_reader_document
    return choose_reader_document(parent, 'pdf')


def activate(context):
    from .ui.reader import open_pdf
    return open_pdf(context.path)


def register():
    from commonUtils.ui.features import FileType, BrowserExtension, FileActivation
    from features.contributions import Feature, DocumentLauncherContribution
    return Feature(id='pdf', label='PDF Reader',
        file_types=[FileType('features.pdf.file_type:PDFFile', extensions=('pdf',))],
        browser=BrowserExtension(activation=[FileActivation('features.pdf.file_type:PDFFile', activate)]),
        document_launchers=[DocumentLauncherContribution('pdf', 'PDF Reader', launch, 'book', 45,
            description='Read PDF documents, jump to pages, and swipe vertically.')])
