"""Page decoding and spread painting, independent of reader window controls."""

from io import BytesIO
from PIL import Image, ImageOps, features as pillow_features

from commonUtils.ui import pyside as qt
from features.comics.reading import visible_pages, SPREAD_GAP

MAX_DISPLAY_PIXELS = 40_000_000
MAX_DISPLAY_SIDE = 6000


class PageCanvas(qt.QWidget):
    resized = qt.Signal()

    def __init__(self):
        super().__init__()
        self.pixmaps = ()
        self.visual_pages = ()
        self.message = 'Loading page…'
        self.setMinimumSize(100, 100)
        self.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Expanding)

    @property
    def pixmap(self):
        return self.pixmaps[0][1] if self.pixmaps else qt.QPixmap()

    def set_pages(self, pages, right_to_left):
        self.pixmaps = tuple(reversed(pages)) if right_to_left else tuple(pages)
        self.visual_pages = tuple(index for index, _ in self.pixmaps)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        painter.fillRect(self.rect(), self.palette().brush(qt.QPalette.ColorRole.Base))
        if not self.pixmaps:
            painter.setPen(self.palette().color(qt.QPalette.ColorRole.Text))
            painter.drawText(self.rect().adjusted(20, 20, -20, -20),
                             qt.Qt.AlignmentFlag.AlignCenter | qt.Qt.TextFlag.TextWordWrap, self.message)
            return
        gap = SPREAD_GAP if len(self.pixmaps) == 2 else 0
        ratios = [pixmap.width() / pixmap.height() for _, pixmap in self.pixmaps]
        height = min(self.height(), (self.width() - gap) / sum(ratios))
        width = sum(ratios) * height + gap
        x, y = (self.width() - width) / 2, (self.height() - height) / 2
        painter.setRenderHint(qt.QPainter.RenderHint.SmoothPixmapTransform)
        for ratio, (_, pixmap) in zip(ratios, self.pixmaps):
            target = qt.QRectF(x, y, ratio * height, height)
            painter.drawPixmap(target, pixmap, qt.QRectF(pixmap.rect()))
            x += target.width() + gap


def _pillow_image(data):
    """Decode to owned pixels without requiring any Qt image-format plugin."""
    with Image.open(BytesIO(data)) as source:
        rgb_profile = source.info.get('icc_profile') if source.mode in ('RGB', 'RGBA') else None
        if source.width * source.height > MAX_DISPLAY_PIXELS:
            # JPEG can reduce during decoding; other formats still retain Pillow's
            # decompression-bomb safeguards. Resize before copying/rotating pixels.
            source.draft(source.mode, (MAX_DISPLAY_SIDE, MAX_DISPLAY_SIDE))
            source.thumbnail((MAX_DISPLAY_SIDE, MAX_DISPLAY_SIDE), Image.Resampling.LANCZOS)
        oriented = ImageOps.exif_transpose(source)
        rgba = oriented.convert('RGBA')
        pixels = rgba.tobytes()
        image = qt.QImage(pixels, rgba.width, rgba.height, rgba.width * 4,
                          qt.QImage.Format.Format_RGBA8888).copy()
        if image.isNull():
            raise ValueError('Could not allocate the decoded page image')
        if rgb_profile:
            color_space = qt.QColorSpace.fromIccProfile(rgb_profile)
            if color_space.isValid():
                image.setColorSpace(color_space)
        return image


def read_image(pages, index):
    entry = pages.pages[index]
    location = f'page {index + 1} ({entry}) in {pages.path.name}'
    try:
        data, mime = pages.read_page(index)
    except Exception as error:
        raise ValueError(f'Could not load {location} from the archive: {error}') from error
    buffer = qt.QBuffer()
    buffer.setData(data)
    buffer.open(qt.QIODevice.OpenModeFlag.ReadOnly)
    reader = qt.QImageReader(buffer)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.width() * size.height() > MAX_DISPLAY_PIXELS:
        reader.setScaledSize(size.scaled(MAX_DISPLAY_SIDE, MAX_DISPLAY_SIDE,
                                        qt.Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if not image.isNull():
        return image
    qt_error = reader.errorString() or 'This page could not be displayed'
    try:
        return _pillow_image(data)
    except Exception as error:
        formats = ', '.join(sorted(bytes(fmt).decode('ascii', errors='replace')
                                   for fmt in qt.QImageReader.supportedImageFormats())) or 'none'
        webp = 'available' if pillow_features.check('webp') else 'unavailable'
        raise ValueError(
            f'Could not decode {location}. Archive entry read: {len(data):,} bytes ({mime}). '
            f'Qt: {qt_error}. Pillow: {error}. '
            f'Qt image formats: {formats}. Pillow WebP support: {webp}. '
            'The page may be damaged or a required image decoder may be unavailable.'
        ) from error


def read_candidates(pages, index, *, decode=None):
    decode = decode or read_image
    images = {index: decode(pages, index)}
    if index + 1 < len(pages.pages) and index not in pages.double_pages and images[index].width() < images[index].height():
        try:
            images[index + 1] = decode(pages, index + 1)
        except KeyError:
            if decode is not read_image:
                raise
        except Exception:
            # A damaged following page must not prevent reading this page.
            pass
    return images


def read_previous(pages, index, viewport, mode, *, decode=None):
    """Choose the previous spread from its actual images after a seek or resize."""
    if index > 0:
        images = read_candidates(pages, index - 1, decode=decode)
        sizes = {page: (image.width(), image.height()) for page, image in images.items()}
        if visible_pages(index - 1, sizes, viewport, mode, pages.double_pages) == (index - 1, index):
            return index - 1, images
    return index, read_candidates(pages, index, decode=decode)
