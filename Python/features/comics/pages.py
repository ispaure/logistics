"""Lazy archive page access and bounded cover rendering without extraction."""

from io import BytesIO
from pathlib import Path
import zipfile

from .archive_io import archive_unchanged
from .library import ComicDocument
from commonUtils.archives.zip_access import open_archive
from commonUtils.search.names import natural_name_key

IMAGE_TYPES = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
               '.webp': 'image/webp', '.gif': 'image/gif', '.bmp': 'image/bmp',
               '.tif': 'image/tiff', '.tiff': 'image/tiff'}
MAX_PAGE_BYTES = 128 * 1024 * 1024


def _image_modules():
    try:
        from PIL import Image, ImageOps
    except ImportError as error:
        raise RuntimeError('Image decoding and cover rendering require the optional Pillow dependency') from error
    return Image, ImageOps


def __getattr__(name):
    # Preserve previous module-level exports for desktop callers.
    if name in ('Image', 'ImageOps'):
        return _image_modules()[0 if name == 'Image' else 1]
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def natural_key(name):
    return natural_name_key(name)


def comic_page_names(archive):
    """Find naturally ordered supported pages using headers only."""
    return sorted((info.filename for info in archive.infolist()
                                 if not info.is_dir() and Path(info.filename).suffix.lower() in IMAGE_TYPES
                                 and '__MACOSX' not in Path(info.filename).parts
                                 and not Path(info.filename).name.startswith('._')), key=natural_key)

def double_page_indices(info, count):
    result = set()
    root = info.xml_root
    for container in root.childNodes:
        if container.localName != 'Pages' or container.namespaceURI != root.namespaceURI:
            continue
        for page in container.childNodes:
            if page.localName != 'Page' or page.namespaceURI != root.namespaceURI:
                continue
            if page.getAttribute('DoublePage').lower() in ('true', '1', 'yes'):
                try:
                    index = int(page.getAttribute('Image'))
                    if 0 <= index < count:
                        result.add(index)
                except ValueError:
                    pass
    return result


class ComicPages:
    def __init__(self, path, document=None, *, password=None):
        self.document = document or ComicDocument(path, password=password)
        self.path = self.document.path
        with self.document.open_archive() as archive:
            self.pages = comic_page_names(archive)
        if not self.pages:
            raise ValueError('This archive contains no supported image pages')
        self.double_pages = double_page_indices(self.document.info, len(self.pages))
        try:
            self.right_to_left = self.document.info.get_field('Manga') == 'YesAndRightToLeft'
        except ValueError:
            self.right_to_left = False

    def read_page(self, index):
        if not 0 <= index < len(self.pages):
            raise IndexError('Page does not exist')
        if not self.document.unchanged():
            raise RuntimeError('The comic changed. Reopen the reader to load the updated archive.')
        name = self.pages[index]
        with self.document.open_archive() as archive:
            if archive.getinfo(name).file_size > MAX_PAGE_BYTES:
                raise ValueError('Page exceeds the supported image size')
            data = archive.read(name)
        if not self.document.unchanged():
            raise RuntimeError('The comic changed while reading this page')
        mime = IMAGE_TYPES[Path(name).suffix.lower()]
        if mime == 'image/tiff':
            Image, ImageOps = _image_modules()
            with Image.open(BytesIO(data)) as image:
                image = ImageOps.exif_transpose(image).convert('RGB')
                result = BytesIO()
                image.save(result, format='PNG')
                return result.getvalue(), 'image/png'
        return data, mime

    def cover(self, size=(360, 500)):
        Image, ImageOps = _image_modules()
        data, _ = self.read_page(0)
        with Image.open(BytesIO(data)) as image:
            image.draft('RGB', size)
            image = ImageOps.exif_transpose(image)
            image.thumbnail(size)
            result = BytesIO()
            image.convert('RGBA').save(result, format='PNG')
            return result.getvalue()


def load_preview(path, size=(960, 1320)):
    document = ComicDocument(path)
    try:
        cover = ComicPages(path, document).cover(size)
        error = ''
    except Exception as issue:
        cover, error = b'', str(issue)
    return document, cover, error
