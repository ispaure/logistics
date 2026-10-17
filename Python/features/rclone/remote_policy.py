"""Portable rules for read-only, memory-only remote documents."""
from pathlib import PurePosixPath

LOCAL_COPY_MESSAGE = ('This file cannot be previewed directly through the remote. '
                      'Please manually make a local copy, then open that copy.')
TEXT = {'.txt', '.md', '.markdown', '.ini'}
IMAGES = {'.png', '.jpg', '.jpeg', '.webp'}
ARCHIVES = {'.epub', '.cbz', '.zip'}
TEXT_LIMIT = 1024 * 1024
IMAGE_LIMIT = 16 * 1024 * 1024


class LocalCopyRequired(ValueError):
    def __init__(self):
        super().__init__(LOCAL_COPY_MESSAGE)


def direct_kind(path, size):
    suffix = PurePosixPath(str(path)).suffix.lower()
    if size < 0:
        raise LocalCopyRequired()
    if suffix in TEXT and size <= TEXT_LIMIT:
        return 'text'
    if suffix in IMAGES and size <= IMAGE_LIMIT:
        return 'image'
    if suffix == '.pdf' and size <= 32 * 1024 * 1024:
        return 'pdf'
    if suffix in ARCHIVES:
        return 'archive'
    raise LocalCopyRequired()
