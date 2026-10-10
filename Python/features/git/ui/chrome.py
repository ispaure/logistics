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
QWidget#gitWorkspace QTreeWidget::item:selected { padding: 1px 4px; margin: 0; }
QWidget#gitWorkspace QHeaderView::section { padding: 2px 4px; }
QWidget#gitWorkspace QWidget#gitSidebar { background: palette(alternate-base); }
QWidget#gitWorkspace QWidget#gitSidebar QTreeWidget { background: transparent; border: none; }
QWidget#gitWorkspace QWidget#gitSidebar QTreeWidget::item:selected { background: #ed851b; color: white; }
QWidget#gitWorkspace QWidget#gitToolbar QToolButton { padding: 4px; border: none; }
QWidget#gitWorkspace QTabWidget::pane { border: none; }
QWidget#gitWorkspace QTabBar::tab { padding: 4px 16px; }
QWidget#gitWorkspace QLabel#fileSection { font-weight: bold; }
'''



def action_icon(name):
    pixmap = qt.QPixmap(28, 28)
    pixmap.fill(qt.Qt.GlobalColor.transparent)
    painter = qt.QPainter(pixmap)
    painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
    painter.setPen(qt.QPen(qt.QColor('#36abe2'), 1.4))
    def line(x1,y1,x2,y2): painter.drawLine(qt.QPointF(x1,y1), qt.QPointF(x2,y2))
    if name in ('commit','pull','push','fetch'):
        painter.drawEllipse(qt.QRectF(4,4,20,20))
        if name == 'commit': line(9,14,19,14); line(14,9,14,19)
        elif name in ('pull','push'):
            top, end = (8,20) if name == 'pull' else (20,8)
            line(14,top,14,end); line(10,end + (-4 if name == 'pull' else 4),14,end); line(18,end + (-4 if name == 'pull' else 4),14,end)
        else:
            painter.drawArc(qt.QRectF(8,8,12,12),30*16,250*16); line(20,8,20,13); line(20,13,16,12)
    elif name in ('branch','merge'):
        line(8,6,8,22); line(8,17,20,10); line(20,10,20,6)
        for x,y in ((8,5),(8,23),(20,5)): painter.drawEllipse(qt.QRectF(x-2,y-2,4,4))
        if name == 'merge': line(12,14,12,19); line(12,19,17,19)
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
        for x,y in ((9,11),(18,11),(9,18),(18,18)): painter.drawEllipse(qt.QRectF(x-2,y-2,4,4))
    else:
        for x in (7,14,21): painter.drawEllipse(qt.QRectF(x-1,13,2,2))
    painter.end()
    return qt.QIcon(pixmap)


def toolbar_button(title, icon, callback, parent):
    button = qt.QToolButton(parent)
    button.setText(title.removesuffix('…'))
    button.setAccessibleName(title)
    button.setToolTip(title)
    button.setIcon(action_icon(icon))
    button.setIconSize(qt.QSize(28,28))
    button.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    button.setMinimumWidth(54)
    button.clicked.connect(callback)
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
