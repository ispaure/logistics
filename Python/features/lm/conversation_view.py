"""Incremental conversation bubbles with native, selectable Markdown bodies."""
import math
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.styling import styling
from commonUtils.ui.markdown.presentation import MarkdownBrowser, style_document


class MessageBrowser(MarkdownBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = None
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setVerticalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Fixed)
        styling().changed.connect(self.refresh_font)
        self.refresh_font()

    def loadResource(self, kind, url):
        return qt.QByteArray()

    def refresh_font(self):
        font = styling().font('reading')
        family = font.family().replace('\\', '\\\\').replace('"', '\\"')
        self.setStyleSheet(f'QTextBrowser {{ background: transparent; border: none; font-family: "{family}"; font-size: {font.pointSizeF()}pt; }}')
        self.document().setDefaultFont(font)
        if self.source is not None:
            self.set_source(self.source, force=True)

    def set_source(self, source, *, force=False):
        if source == self.source and not force:
            return
        self.source = source
        cursor = self.textCursor()
        position, anchor = cursor.position(), cursor.anchor()
        self.document().setMarkdown(source, qt.QTextDocument.MarkdownFeature.MarkdownDialectGitHub |
                                    qt.QTextDocument.MarkdownFeature.MarkdownNoHTML)
        style_document(self.document(), self.palette(), callouts={})
        self.document().setDocumentMargin(8)
        cursor = qt.QTextCursor(self.document())
        end = self.document().characterCount() - 1
        cursor.setPosition(min(anchor, end))
        cursor.setPosition(min(position, end), qt.QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        self.fit_height()

    def fit_height(self):
        self.document().setTextWidth(max(80, self.viewport().width()))
        height = math.ceil(self.document().size().height()) + 4
        if self.horizontalScrollBar().isVisible():
            height += self.horizontalScrollBar().height()
        if self.height() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_height()


class Bubble(qt.QFrame):
    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.role = entry['role']
        self.setObjectName('userBubble' if self.role == 'user' else 'assistantBubble')
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(2)
        self.label = qt.QLabel()
        self.label.setForegroundRole(qt.QPalette.ColorRole.PlaceholderText)
        self.label.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.browser = MessageBrowser(self)
        layout.addWidget(self.label)
        layout.addWidget(self.browser)
        self.update_entry(entry)

    def update_entry(self, entry):
        name = 'You' if self.role == 'user' else 'Assistant'
        self.label.setText(name if entry['status'] == 'complete' else f'{name} · {entry["status"]}')
        if self.role == 'user':
            light = self.palette().color(qt.QPalette.ColorRole.Base).lightness()
            gray = max(0, min(255, light + (14 if light < 128 else -14)))
            self.setStyleSheet(f'QFrame#userBubble {{ background: rgb({gray}, {gray}, {gray}); border-radius: 12px; }}')
        self.browser.set_source(entry['content'])


class ConversationView(qt.QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.body = qt.QWidget()
        self.box = qt.QVBoxLayout(self.body)
        self.box.setContentsMargins(12, 8, 12, 8)
        self.box.setSpacing(12)
        self.box.addStretch()
        self.setWidget(self.body)
        self.bubbles = {}
        self.rows = {}
        self.key = None
        self.follow_bottom = True
        self.verticalScrollBar().rangeChanged.connect(self._range_changed)
        self.verticalScrollBar().valueChanged.connect(self._scrolled)

    def _scrolled(self, value):
        self.follow_bottom = value >= self.verticalScrollBar().maximum() - 12

    def _range_changed(self, low, high):
        if self.follow_bottom:
            bar = self.verticalScrollBar()
            bar.blockSignals(True)
            bar.setValue(high)
            bar.blockSignals(False)

    def loadResource(self, kind, url):
        return qt.QByteArray()

    def sync(self, data):
        key = data['id'] if data else None
        if key != self.key:
            for row in self.rows.values():
                self.box.removeWidget(row)
                row.deleteLater()
            self.bubbles.clear()
            self.rows.clear()
            self.key = key
        for entry in data['messages'] if data else []:
            bubble = self.bubbles.get(entry['id'])
            if bubble is None:
                row = qt.QWidget(self.body)
                layout = qt.QHBoxLayout(row)
                layout.setContentsMargins(0, 0, 0, 0)
                bubble = Bubble(entry, row)
                if entry['role'] == 'user':
                    layout.addStretch(1)
                layout.addWidget(bubble, 4)
                self.box.insertWidget(self.box.count() - 1, row)
                self.bubbles[entry['id']] = bubble
                self.rows[entry['id']] = row
            else:
                bubble.update_entry(entry)
        valid = {entry['id'] for entry in data['messages']} if data else set()
        for key in list(self.rows):
            if key not in valid:
                self.box.removeWidget(self.rows[key])
                self.rows.pop(key).deleteLater()
                self.bubbles.pop(key)

    def clear(self):
        self.sync(None)
