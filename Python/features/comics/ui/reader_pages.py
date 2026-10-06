"""Page decoding and spread painting, independent of reader window controls."""

from commonUtils.ui import pyside as qt
from features.comics.reading import visible_pages, SPREAD_GAP


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


def read_image(pages, index):
    data, _ = pages.read_page(index)
    buffer = qt.QBuffer()
    buffer.setData(data)
    buffer.open(qt.QIODevice.OpenModeFlag.ReadOnly)
    reader = qt.QImageReader(buffer)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.width() * size.height() > 40_000_000:
        reader.setScaledSize(size.scaled(6000, 6000, qt.Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        raise ValueError(reader.errorString() or 'This page could not be displayed')
    return image


def read_candidates(pages, index):
    images = {index: read_image(pages, index)}
    if index + 1 < len(pages.pages) and index not in pages.double_pages and images[index].width() < images[index].height():
        try:
            images[index + 1] = read_image(pages, index + 1)
        except Exception:
            # A damaged following page must not prevent reading this page.
            pass
    return images


def read_previous(pages, index, viewport, mode):
    """Choose the previous spread from its actual images after a seek or resize."""
    if index > 0:
        images = read_candidates(pages, index - 1)
        sizes = {page: (image.width(), image.height()) for page, image in images.items()}
        if visible_pages(index - 1, sizes, viewport, mode, pages.double_pages) == (index - 1, index):
            return index - 1, images
    return index, read_candidates(pages, index)
