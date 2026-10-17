"""Local provider adapter; PDFs are opened directly without library imports."""
from commonUtils.runtime.operations import check_cancelled
from services.documents.readers import PrivateReader


class PDFCopies:
    encrypted = False
    offline = True

    def __init__(self, provider):
        self.provider = provider
        self.root = provider.root

    def open(self, key, *, password='', cancelled=lambda: False):
        check_cancelled(cancelled)
        reader = PrivateReader(key, source=self.provider)
        check_cancelled(cancelled)
        reader.key, reader.read_only = key, True
        return reader
