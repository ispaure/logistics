"""Palette-aware chat action glyphs."""
from commonUtils.ui import pyside as qt


class ChatIcon(qt.QIconEngine):
    def __init__(self, name, color=None):
        super().__init__()
        self.name = name
        self.color = color

    def clone(self):
        return ChatIcon(self.name, self.color)

    def paint(self, painter, rect, mode, state):
        painter.save()
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        painter.translate(rect.x(), rect.y())
        painter.scale(rect.width() / 24, rect.height() / 24)
        palette = qt.QApplication.palette()
        role = qt.QPalette.ColorRole.HighlightedText if self.name in ('send', 'stop') else qt.QPalette.ColorRole.ButtonText
        color = palette.color(role if mode != qt.QIcon.Mode.Disabled else qt.QPalette.ColorRole.PlaceholderText)
        if self.color is not None and mode != qt.QIcon.Mode.Disabled:
            color = qt.QColor(self.color)
        pen = qt.QPen(color, 2)
        pen.setCapStyle(qt.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(qt.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        if self.name == 'stop':
            painter.setBrush(color)
            painter.drawRoundedRect(qt.QRectF(6, 6, 12, 12), 2, 2)
        elif self.name == 'send':
            painter.drawLine(qt.QLineF(12, 19, 12, 5))
            painter.drawPolyline(qt.QPolygonF([qt.QPointF(6, 11), qt.QPointF(12, 5), qt.QPointF(18, 11)]))
        elif self.name == 'copy':
            painter.drawRoundedRect(qt.QRectF(8, 8, 12, 13), 2, 2)
            painter.drawPolyline(qt.QPolygonF([qt.QPointF(5, 16), qt.QPointF(3, 16), qt.QPointF(3, 3), qt.QPointF(15, 3), qt.QPointF(15, 5)]))
        elif self.name == 'refresh':
            painter.drawArc(qt.QRectF(4, 4, 16, 16), 45 * 16, 285 * 16)
            painter.drawPolyline(qt.QPolygonF([qt.QPointF(15, 3), qt.QPointF(20, 4), qt.QPointF(19, 9)]))
        elif self.name in ('speaker', 'speaker_stop'):
            painter.drawPolygon(qt.QPolygonF([qt.QPointF(3, 9), qt.QPointF(7, 9), qt.QPointF(12, 5),
                                             qt.QPointF(12, 19), qt.QPointF(7, 15), qt.QPointF(3, 15)]))
            if self.name == 'speaker_stop':
                painter.drawLine(qt.QLineF(16, 9, 22, 15))
                painter.drawLine(qt.QLineF(16, 15, 22, 9))
            else:
                painter.drawArc(qt.QRectF(10, 7, 10, 10), -60 * 16, 120 * 16)
                painter.drawArc(qt.QRectF(8, 3, 18, 18), -50 * 16, 100 * 16)
        elif self.name == 'plus':
            painter.drawLine(qt.QLineF(4, 12, 20, 12))
            painter.drawLine(qt.QLineF(12, 4, 12, 20))
        elif self.name == 'new':
            painter.drawRoundedRect(qt.QRectF(5, 3, 14, 18), 2, 2)
            painter.drawLine(qt.QLineF(8, 12, 16, 12))
            painter.drawLine(qt.QLineF(12, 8, 12, 16))
        elif self.name == 'folder':
            path = qt.QPainterPath()
            path.moveTo(3, 7); path.lineTo(3, 4); path.lineTo(10, 4)
            path.lineTo(12, 7); path.lineTo(21, 7); path.lineTo(21, 20)
            path.lineTo(3, 20); path.closeSubpath()
            painter.drawPath(path)
            painter.drawLine(qt.QLineF(8, 13, 16, 13))
            painter.drawLine(qt.QLineF(12, 9, 12, 17))
        elif self.name == 'more':
            painter.setBrush(color)
            for x in (5, 12, 19):
                painter.drawEllipse(qt.QPointF(x, 12), 1, 1)
        elif self.name == 'settings':
            for y, x in ((5, 8), (12, 16), (19, 10)):
                painter.drawLine(qt.QLineF(3, y, 21, y))
                painter.setBrush(palette.color(qt.QPalette.ColorRole.Window))
                painter.drawEllipse(qt.QPointF(x, y), 2.5, 2.5)
        painter.restore()

    def pixmap(self, size, mode, state):
        result = qt.QPixmap(size)
        if result.isNull():
            return result
        result.fill(qt.Qt.GlobalColor.transparent)
        painter = qt.QPainter(result)
        self.paint(painter, qt.QRect(qt.QPoint(), size), mode, state)
        painter.end()
        return result


def chat_icon(name, color=None):
    return qt.QIcon(ChatIcon(name, color))


def action_button(title, callback, icon, *, size=20, parent=None):
    """Consistent named, palette-aware controls for page and message actions."""
    button = qt.QToolButton(parent)
    button.setAutoRaise(True)
    button.setIcon(chat_icon(icon))
    button.setIconSize(qt.QSize(size, size))
    button.setToolTip(title)
    button.setAccessibleName(title)
    button.clicked.connect(callback)
    return button
