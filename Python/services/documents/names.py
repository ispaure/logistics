"""Portable validation of text document display names."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"


def document_name(name):
    if (not isinstance(name, str) or not name.strip() or len(name) > 200
            or any(ord(c) < 32 or c in '/\\' for c in name)):
        raise ValueError('Use a document name without slashes or control characters.')
    return name.strip()

