"""Feature-local toolbar drawing and workspace styling; no shared theme changes."""
import re
import math
from urllib.parse import urlsplit, urlunsplit
from commonUtils.ui import pyside as qt

# Keep the application's palette, native controls and theme. Only density and
# the repository navigation accent belong to this workspace.
WORKSPACE_STYLE = '''
QWidget#gitWorkspace QTreeWidget::item,
QWidget#gitWorkspace QTreeWidget::item:hover,
QWidget#gitWorkspace QTreeWidget::item:selected { padding: 2px 4px; margin: 0; }
QWidget#gitWorkspace QHeaderView::section { padding: 2px 4px; }
QWidget#gitWorkspace QWidget#gitSidebar { background: palette(alternate-base); }
QWidget#gitWorkspace QWidget#gitSidebar QTreeWidget { background: transparent; border: none; }
QWidget#gitWorkspace QWidget#gitSidebar QTreeWidget::item { padding: 3px 4px; }
QWidget#gitWorkspace QWidget#gitSidebar QTreeWidget::item:selected { background: #ed851b; color: white; }
QWidget#gitWorkspace QWidget#gitToolbar QToolButton { padding: 4px; border: none; }
QWidget#gitWorkspace QTabWidget::pane { border: none; }
QWidget#gitWorkspace QTabBar::tab { padding: 4px 16px; }
QWidget#gitWorkspace QLabel#fileSection { font-weight: bold; }
'''

# Okabe–Ito hues: use shape/letters as well as color for status information.
GRAPH_COLORS = ('#56B4E9', '#D55E00', '#F0E442', '#009E73', '#CC79A7', '#E69F00', '#0072B2')


def status_icon(status):
    code = status[:1]
    color = {'A': '#009E73', '?': '#56B4E9', 'M': '#E69F00', 'D': '#D55E00',
             'R': '#56B4E9', 'C': '#CC79A7', '!': '#D55E00', 'U': '#D55E00'}.get(code, '#8b96a5')
    pixmap = qt.QPixmap(16, 16); pixmap.fill(qt.Qt.GlobalColor.transparent)
    painter = qt.QPainter(pixmap)
    painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
    painter.setPen(qt.Qt.PenStyle.NoPen); painter.setBrush(qt.QColor(color))
    painter.drawRoundedRect(qt.QRectF(1, 1, 14, 14), 3, 3)
    painter.setPen(qt.QColor('#101820'))
    font = qt.QFont(); font.setPixelSize(11); font.setBold(True); painter.setFont(font)
    mark = {'A': '+', 'D': '−', 'M': 'M', 'R': '→', 'C': 'C', 'U': '!'}.get(code, code or '·')
    painter.drawText(qt.QRect(1, 0, 14, 16), qt.Qt.AlignmentFlag.AlignCenter, mark)
    painter.end()
    return qt.QIcon(pixmap)



def action_icon(name, count=0):
    # Supply native-resolution artwork rather than enlarging a 28px bitmap on Retina.
    icon = qt.QIcon()
    for scale in (1, 2, 3, 4):
        pixmap = qt.QPixmap(28 * scale, 28 * scale)
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(qt.Qt.GlobalColor.transparent)
        painter = qt.QPainter(pixmap)
        _draw_action(painter, name)
        if count:
            label = str(count) if count < 100 else '99+'
            width = max(11, 5 * len(label) + 4)
            rect = qt.QRectF(28 - width, 0, width, 12)
            painter.setPen(qt.Qt.PenStyle.NoPen)
            painter.setBrush(qt.QColor('#216ab4'))
            painter.drawRoundedRect(rect, 3, 3)
            font = qt.QFont(); font.setPixelSize(9); font.setBold(True)
            painter.setFont(font); painter.setPen(qt.QColor('white'))
            painter.drawText(rect, qt.Qt.AlignmentFlag.AlignCenter, label)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def _draw_action(painter, name):
    painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
    painter.setPen(qt.QPen(qt.QColor('#36abe2'), 1.8, qt.Qt.PenStyle.SolidLine,
                               qt.Qt.PenCapStyle.RoundCap, qt.Qt.PenJoinStyle.RoundJoin))
    def line(x1,y1,x2,y2): painter.drawLine(qt.QPointF(x1,y1), qt.QPointF(x2,y2))
    if name in ('commit','pull','push','fetch'):
        painter.drawEllipse(qt.QRectF(4,4,20,20))
        if name == 'commit': line(8,14,12,18); line(12,18,20,10)
        elif name in ('pull','push'):
            top, end = (8,20) if name == 'pull' else (20,8)
            line(14,top,14,end); line(10,end + (-4 if name == 'pull' else 4),14,end); line(18,end + (-4 if name == 'pull' else 4),14,end)
        else:
            painter.drawArc(qt.QRectF(8,8,12,12),30*16,250*16); line(20,8,20,13); line(20,13,16,12)
    elif name in ('branch','merge'):
        line(8,6,8,22)
        if name == 'branch': line(8,17,20,10); line(20,10,20,6)
        else: line(20,6,20,11); line(20,11,8,19)
        for x,y in ((8,5),(8,23),(20,5)): painter.drawEllipse(qt.QRectF(x-2,y-2,4,4))
        if name == 'merge': line(8,19,13,16); line(8,19,13,21)
    elif name == 'template':
        painter.drawRoundedRect(qt.QRectF(6,3,16,22),1,1)
        for y in (9,13,17,21): line(10,y,18,y)
    elif name == 'security':
        painter.drawRoundedRect(qt.QRectF(6,12,16,12),2,2)
        painter.drawArc(qt.QRectF(9,3,10,16),0,180*16)
        line(9,10,9,12); line(19,10,19,12); line(14,16,14,20)
    elif name == 'terminal':
        painter.drawRoundedRect(qt.QRectF(3,6,22,16),2,2); line(7,10,11,14); line(11,14,7,18); line(14,18,20,18)
    elif name == 'remote':
        painter.drawEllipse(qt.QRectF(4,4,20,20)); painter.drawEllipse(qt.QRectF(10,4,8,20)); line(4,14,24,14)
    elif name == 'folder':
        painter.drawRect(qt.QRectF(4,9,20,14)); line(4,9,4,5); line(4,5,12,5); line(12,5,15,9)
    elif name == 'settings':
        painter.drawEllipse(qt.QRectF(7,7,14,14)); painter.drawEllipse(qt.QRectF(11,11,6,6))
        for i in range(8):
            angle=i*math.pi/4
            line(14+7*math.cos(angle),14+7*math.sin(angle),14+11*math.cos(angle),14+11*math.sin(angle))
    elif name == 'stash':
        painter.drawRect(qt.QRectF(4,6,20,17))
        line(4,11,24,11); line(11,15,17,15)
    else:
        for x in (7,14,21): painter.drawEllipse(qt.QRectF(x-1,13,2,2))



def toolbar_button(title, icon, callback, parent):
    # Real actions remain available in Qt's overflow menu on narrow/floating panes.
    action = qt.QAction(action_icon(icon), title.removesuffix('…'), parent)
    action.setToolTip(title)
    action.triggered.connect(callback)
    parent.addAction(action)
    button = parent.widgetForAction(action)
    button.setAccessibleName(title)
    button.setMinimumWidth(54)
    return button


def browser_remote_url(address):
    """Open only known HTTP/SSH forms; never hand custom Git schemes to a browser."""
    address = address.strip()
    scp = re.fullmatch(r'(?:[^@/:]+@)?([\w.-]+):([^:\s][^\s]*)', address)
    if scp and '://' not in address and not re.match(r'^[A-Za-z]:[/\\]',address): address = 'https://' + scp[1] + '/' + scp[2]
    try:
        parts = urlsplit(address)
        port = parts.port
    except ValueError: return ''
    if parts.scheme not in ('http','https','ssh') or not parts.hostname: return ''
    if parts.password or parts.query or parts.fragment: return ''
    host = parts.hostname
    if ':' in host: host = '[' + host + ']'
    if parts.scheme != 'ssh' and port: host += ':' + str(port)
    return urlunsplit(('https' if parts.scheme == 'ssh' else parts.scheme, host, parts.path.removesuffix('.git'), '', ''))
