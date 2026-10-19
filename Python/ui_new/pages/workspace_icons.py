"""Qt rendering of the mobile Workspaces folder artwork."""
from commonUtils.ui import pyside as qt
from services.folders.appearance import FOLDER_PATHS, LOCK_LIGHT, LOCK_DARK


def folder_icon(widget, state=None):
    name = 'cloud' if state == 'cloud' else 'folder_' + state if state else 'folder'
    dark = widget.palette().color(qt.QPalette.ColorRole.Base).lightness() < 128
    colour = qt.QColor((LOCK_DARK if dark else LOCK_LIGHT)[name]) if name in LOCK_LIGHT else widget.palette().color(qt.QPalette.ColorRole.Highlight)
    pixmap = qt.QPixmap(72, 72)
    pixmap.fill(qt.Qt.GlobalColor.transparent)
    painter = qt.QPainter(pixmap)
    painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
    painter.scale(3, 3)
    pen = qt.QPen(colour, 1.6)
    pen.setCapStyle(qt.Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(qt.Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    for points in FOLDER_PATHS[name]:
        path = qt.QPainterPath(qt.QPointF(*points[0]))
        for point in points[1:]:
            path.lineTo(qt.QPointF(*point))
        painter.drawPath(path)
    painter.end()
    icon = qt.QIcon(pixmap)
    icon.addPixmap(pixmap, qt.QIcon.Mode.Selected)
    return icon
