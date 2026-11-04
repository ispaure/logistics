"""Qt rendering of the same entry artwork used by the mobile browser."""
from base64 import b64decode
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.icons import painted_icon
from services.documents.entry_icons import ENTRY_ICONS


class EntryArtwork:
    def __init__(self, kind):
        self.image = qt.QImage.fromData(b64decode(ENTRY_ICONS[kind]))

    def paint(self, painter, rect, mode, state):
        image = self.image.copy()
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
        painter.setRenderHint(qt.QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(rect, image)


def entry_icon(directory, *, landing_page=False):
    kind = 'folder_document' if directory and landing_page else 'files' if directory else 'documents'
    return painted_icon(EntryArtwork, kind)


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
