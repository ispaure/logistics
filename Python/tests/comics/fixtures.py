"""Small immutable page payloads; every test still owns its archive and state."""

from functools import lru_cache
from io import BytesIO
from unittest.mock import patch

from PIL import Image


@lru_cache(maxsize=32)
def encoded_page(color='orange', size=(80, 120)):
    stream = BytesIO()
    with Image.new('RGB', size, color) as image:
        image.save(stream, format='PNG')
    return stream.getvalue()


def comic_library(root, *, folder_sizes=False):
    """Use real comic/browser UI; opt in to the shared persistent size index."""
    from commonUtils.ui.file_browser import FileBrowser
    from features.comics.ui import library

    def browser(*args, **kwargs):
        return FileBrowser(*args, calculate_folder_sizes=folder_sizes, **kwargs)

    with patch.object(library, 'FileBrowser', side_effect=browser):
        return library.ComicLibraryWindow(root)
