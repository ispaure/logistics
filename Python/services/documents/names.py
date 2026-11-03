"""Portable validation of text document display names."""


def document_name(name):
    if (not isinstance(name, str) or not name.strip() or len(name) > 200
            or any(ord(c) < 32 or c in '/\\' for c in name)):
        raise ValueError('Use a document name without slashes or control characters.')
    return name.strip()

