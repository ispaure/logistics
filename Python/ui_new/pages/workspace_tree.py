"""Compact always-expanded groups and connector lines for desktop Workspaces."""
from commonUtils.ui import pyside as qt


class WorkspaceTree(qt.QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemsExpandable(False)
        self.setExpandsOnDoubleClick(False)
        self.setRootIsDecorated(False)
        self.setIndentation(20)
        self.setIconSize(qt.QSize(18, 18))
        self.setStyleSheet('''
            QTreeWidget::item { min-height: 24px; padding: 1px 2px; }
            QTreeWidget::item:selected { background: palette(alternate-base); color: palette(text);
                                        border-left: 3px solid palette(highlight); }
        ''')

    def drawBranches(self, painter, rect, index):
        parent = index.parent()
        if not parent.isValid():
            return
        dark = self.palette().color(qt.QPalette.ColorRole.Base).lightness() < 128
        painter.save()
        painter.setPen(qt.QPen(qt.QColor('#737f90' if dark else '#a8b2c1'), 1.5))
        x = rect.right() - self.indentation() // 2
        y = rect.center().y()
        sibling = index.sibling(index.row() + 1, 0).isValid()
        painter.drawLine(x, rect.top(), x, rect.bottom() if sibling else y)
        painter.drawLine(x, y, rect.right(), y)
        ancestor = parent
        x -= self.indentation()
        while ancestor.parent().isValid():
            if ancestor.sibling(ancestor.row() + 1, 0).isValid():
                painter.drawLine(x, rect.top(), x, rect.bottom())
            ancestor = ancestor.parent()
            x -= self.indentation()
        painter.restore()
