"""Compatibility adapter for PDF documents over the common provider boundary."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from services.documents.provider_documents import ProviderDocuments


class PDFCopies(ProviderDocuments):
    pass
