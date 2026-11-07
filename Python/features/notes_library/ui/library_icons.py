"""Qt rendering of the same entry artwork used by the mobile browser."""
from base64 import b64decode
from functools import lru_cache
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.icons import painted_icon
from commonUtils.ui.file_browser.navigation import BreadcrumbSeparator
from services.documents.entry_icons import ENTRY_ICONS


class EntryArtwork:
    def __init__(self, kind):
        self.image = qt.QImage.fromData(b64decode(ENTRY_ICONS[kind]))

    def paint(self, painter, rect, mode, state):
        ratio = painter.device().devicePixelRatioF()
        image = self.image.scaled(rect.size() * ratio, qt.Qt.AspectRatioMode.KeepAspectRatio,
                                  qt.Qt.TransformationMode.SmoothTransformation)
        tint = qt.QPainter(image)
        try:
            tint.setCompositionMode(qt.QPainter.CompositionMode.CompositionMode_SourceIn)
            group = (qt.QPalette.ColorGroup.Disabled if mode == qt.QIcon.Mode.Disabled
                     else qt.QPalette.ColorGroup.Active)
            role = (qt.QPalette.ColorRole.HighlightedText if mode == qt.QIcon.Mode.Selected
                    else qt.QPalette.ColorRole.Highlight)
            tint.fillRect(image.rect(), qt.QApplication.palette().color(group, role))
        finally:
            tint.end()
        painter.drawImage(rect, image)


def entry_icon(directory, *, landing_page=False):
    kind = 'folder_document' if directory and landing_page else 'files' if directory else 'documents'
    return painted_icon(EntryArtwork, kind)


@lru_cache(maxsize=12)
def breadcrumb_icon_source(directory, landing_page, palette_key):
    """Embed the same tinted entry icon in the breadcrumb's rich text."""
    pixmap = entry_icon(directory, landing_page=landing_page).pixmap(32)
    return png_source(pixmap)


@lru_cache(maxsize=8)
def breadcrumb_chevron_source(color):
    width = BreadcrumbSeparator.WIDTH
    image = qt.QImage(width * 3, width * 3, qt.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(qt.Qt.GlobalColor.transparent)
    with qt.QPainter(image) as painter:
        painter.scale(3, 3)
        BreadcrumbSeparator.paint_chevron(painter, width, width, qt.QColor(color))
    return png_source(image)


def png_source(image):
    buffer = qt.QBuffer()
    buffer.open(qt.QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    return 'data:image/png;base64,' + bytes(buffer.data().toBase64()).decode('ascii')


class ActionArtwork:
    def __init__(self, kind):
        from services.documents.library_action_icons import ACTION_ICONS
        self.paths = ACTION_ICONS[kind][2]

    def paint(self, painter, rect, mode, state):
        painter.save()
        try:
            painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
            painter.translate(rect.x(), rect.y())
            painter.scale(rect.width() / 24, rect.height() / 24)
            group = (qt.QPalette.ColorGroup.Disabled if mode == qt.QIcon.Mode.Disabled
                     else qt.QPalette.ColorGroup.Active)
            painter.setPen(qt.QPen(qt.QApplication.palette().color(group, qt.QPalette.ColorRole.ButtonText), 1.8))
            for points in self.paths:
                path = qt.QPainterPath(qt.QPointF(*points[0]))
                for point in points[1:]:
                    path.lineTo(qt.QPointF(*point))
                painter.drawPath(path)
        finally:
            painter.restore()
