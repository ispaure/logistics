"""Video-specific line glyphs using the shared palette-aware icon renderer."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.icons import set_painted_icon
from commonUtils.ui.readers.reader_chrome import ReaderIcon


class VideoIcon(ReaderIcon):
    def paint(self, painter, rect, mode, state):
        if self.name in {'play', 'pause', 'speaker', 'fullscreen', 'close', 'reset',
                         'previous-file', 'next-file'}:
            return super().paint(painter, rect, mode, state)
        painter.save()
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        painter.translate(rect.x(), rect.y())
        painter.scale(rect.width() / 24, rect.height() / 24)
        group = qt.QPalette.ColorGroup.Disabled if mode == qt.QIcon.Mode.Disabled else qt.QPalette.ColorGroup.Active
        role = qt.QPalette.ColorRole.Highlight if state == qt.QIcon.State.On else qt.QPalette.ColorRole.ButtonText
        pen = qt.QPen(qt.QApplication.palette().color(group, role), 1.7)
        pen.setCapStyle(qt.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(qt.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(qt.Qt.BrushStyle.NoBrush)
        if self.name in ('back10', 'forward10'):
            if self.name == 'forward10':
                painter.translate(24, 0)
                painter.scale(-1, 1)
            painter.drawArc(qt.QRectF(3, 3, 18, 18), 45 * 16, -295 * 16)
            painter.drawPolyline([qt.QPointF(8, 2), qt.QPointF(3, 5), qt.QPointF(7, 8)])
            if self.name == 'forward10':
                painter.scale(-1, 1)
                painter.translate(-24, 0)
            font = painter.font()
            font.setPixelSize(9)
            painter.setFont(font)
            painter.drawText(qt.QRectF(4, 5, 16, 15), qt.Qt.AlignmentFlag.AlignCenter, '10')
        elif self.name == 'heart':
            path = qt.QPainterPath(qt.QPointF(12, 21))
            path.cubicTo(9, 18, 2, 13, 2, 8)
            path.cubicTo(2, 2, 9, 1, 12, 7)
            path.cubicTo(15, 1, 22, 2, 22, 8)
            path.cubicTo(22, 13, 15, 18, 12, 21)
            painter.drawPath(path)
        elif self.name == 'folder':
            painter.drawPolygon([qt.QPointF(3, 6), qt.QPointF(9, 6), qt.QPointF(11, 8),
                                 qt.QPointF(21, 8), qt.QPointF(21, 19), qt.QPointF(3, 19)])
        elif self.name == 'cast':
            painter.drawRoundedRect(qt.QRectF(3, 4, 18, 15), 2, 2)
            painter.drawLine(qt.QLineF(9, 22, 15, 22))
            painter.drawLine(qt.QLineF(12, 19, 12, 22))
        elif self.name == 'captions':
            painter.drawRoundedRect(qt.QRectF(3, 5, 18, 14), 2, 2)
            for x in (6, 13):
                painter.drawPolyline([qt.QPointF(x + 4, 9), qt.QPointF(x, 9),
                                      qt.QPointF(x, 15), qt.QPointF(x + 4, 15)])
        elif self.name == 'queue':
            painter.drawPolygon([qt.QPointF(3, 6), qt.QPointF(9, 6), qt.QPointF(11, 8),
                                 qt.QPointF(21, 8), qt.QPointF(21, 19), qt.QPointF(3, 19)])
            painter.drawLine(qt.QLineF(7, 12, 17, 12))
            painter.drawLine(qt.QLineF(7, 15, 17, 15))
        elif self.name == 'chapters':
            for y in (6, 12, 18):
                painter.drawLine(qt.QLineF(9, y, 21, y))
                painter.drawEllipse(qt.QRectF(3, y - 1, 2, 2))
        elif self.name == 'picture':
            painter.drawRoundedRect(qt.QRectF(3, 5, 18, 14), 1, 1)
            painter.drawPolyline([qt.QPointF(6, 16), qt.QPointF(10, 11), qt.QPointF(14, 15), qt.QPointF(18, 10)])
        elif self.name == 'audio':
            for x, height in ((4, 6), (8, 14), (12, 20), (16, 10), (20, 16)):
                painter.drawLine(qt.QLineF(x, 12 - height / 2, x, 12 + height / 2))
        elif self.name == 'muted':
            painter.drawPolygon([qt.QPointF(3, 9), qt.QPointF(7, 9), qt.QPointF(12, 5),
                                 qt.QPointF(12, 19), qt.QPointF(7, 15), qt.QPointF(3, 15)])
            painter.drawLine(qt.QLineF(16, 9, 22, 15))
            painter.drawLine(qt.QLineF(16, 15, 22, 9))
        elif self.name == 'more':
            for x in (5, 12, 19):
                painter.drawEllipse(qt.QRectF(x - 1, 11, 2, 2))
        painter.restore()


def video_icon(target, name):
    set_painted_icon(target, VideoIcon, name)


def video_button(parent, label, icon, callback):
    button = qt.QToolButton(parent)
    button.setAutoRaise(True)
    button.setMinimumSize(36, 36)
    button.setIconSize(qt.QSize(21, 21))
    button.setText(label)
    button.setAccessibleName(label)
    button.setToolTip(label)
    if icon:
        video_icon(button, icon)
    button.clicked.connect(callback)
    return button
