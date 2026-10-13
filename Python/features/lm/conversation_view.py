"""Incremental conversation bubbles with native, selectable Markdown bodies."""
from commonUtils.ui.appearance.typography import point_size
import math
from datetime import datetime
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.styling import styling
from commonUtils.ui.markdown.presentation import MarkdownBrowser, style_document
from .image_view import ScreenshotView
from .icons import action_button


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
        theme = getattr(qt.QApplication.instance(), '_commonutils_theme', None)
        if theme is not None:
            theme.changed.connect(self.refresh_font)
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
        style_document(self.document(), qt.QApplication.palette(), callouts={})
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
    retry_requested = qt.Signal()

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
        styling().bind(self.label, 'ui')
        header = qt.QHBoxLayout()
        header.addWidget(self.label)
        header.addStretch()
        self.copy_button = action_button('Copy message as written',
            lambda: qt.QApplication.clipboard().setText(self.browser.source or ''), 'copy', size=16)
        self.browser = MessageBrowser(self)
        self.error = qt.QLabel()
        self.error.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        self.error.setForegroundRole(qt.QPalette.ColorRole.PlaceholderText)
        layout.addLayout(header)
        layout.addWidget(self.browser)
        self.images_box = qt.QWidget()
        self.images_layout = qt.QVBoxLayout(self.images_box)
        self.images_layout.setContentsMargins(0, 0, 0, 0)
        self.image_ids = None
        self.images = []
        layout.addWidget(self.images_box)
        layout.addWidget(self.error)
        footer = qt.QHBoxLayout()
        footer.setSpacing(4)
        footer.addWidget(self.copy_button)
        self.retry_button = action_button('Retry / Regenerate last response', self.retry_requested, 'refresh', size=16)
        self.retry_button.hide()
        footer.addWidget(self.retry_button)
        footer.addStretch()
        self.timestamp = qt.QLabel()
        self.timestamp.setTextFormat(qt.Qt.TextFormat.PlainText)
        footer.addWidget(self.timestamp)
        layout.addLayout(footer)
        styling().changed.connect(self.refresh_chrome)
        theme = getattr(qt.QApplication.instance(), '_commonutils_theme', None)
        if theme is not None:
            theme.changed.connect(self.refresh_chrome)
        self.update_entry(entry)

    def refresh_chrome(self):
        # Local stylesheets can retain the previous Base palette; always obtain
        # theme colors from the application, rather than sampling the bubble.
        muted = qt.QApplication.palette().color(qt.QPalette.ColorRole.PlaceholderText).name()
        self.timestamp.setStyleSheet(f'color: {muted}; font-size: {point_size(6.75)}pt;')
        if self.role == 'user':
            self.setStyleSheet('QFrame#userBubble { background: palette(alternate-base); border-radius: 12px; }')

    def update_entry(self, entry):
        name = 'You' if self.role == 'user' else 'Assistant'
        self.label.setText(name if entry['status'] == 'complete' else f'{name} · {entry["status"]}')
        try:
            created = datetime.fromisoformat(entry.get('created', '')).astimezone()
            self.timestamp.setText(created.strftime('%b %d · %H:%M'))
            self.timestamp.setToolTip(created.strftime('%Y-%m-%d %H:%M:%S %Z'))
        except (TypeError, ValueError):
            self.timestamp.clear()
        self.refresh_chrome()
        error = entry.get('error', '')
        self.error.setText(error)
        self.error.setVisible(bool(error))
        self.browser.set_source(entry['content'])
        images = entry.get('images', [])
        ids = [image['id'] for image in images]
        if ids != self.image_ids:
            while self.images_layout.count():
                item = self.images_layout.takeAt(0)
                item.widget().hide()
                item.widget().deleteLater()
            self.images = [ScreenshotView(image, self.images_box) for image in images]
            for image in self.images:
                self.images_layout.addWidget(image)
            self.image_ids = ids
        self.images_box.setVisible(bool(images))


class ConversationView(qt.QScrollArea):
    retry_requested = qt.Signal()

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
        self.retry_enabled = False
        self.verticalScrollBar().rangeChanged.connect(self._range_changed)
        self.verticalScrollBar().valueChanged.connect(self._scrolled)
        styling().changed.connect(self._fit_bubbles)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'bubbles'):
            self._fit_bubbles()

    def _fit_bubbles(self):
        available = max(100, self.viewport().width() - 24)
        for bubble in self.bubbles.values():
            if bubble.role == 'user':
                text = bubble.browser.document().toPlainText()
                metrics = bubble.browser.fontMetrics()
                natural = max((metrics.horizontalAdvance(line) for line in text.splitlines()), default=0) + 40
                if bubble.images:
                    natural = max(natural, 440)
                bubble.setFixedWidth(min(round(available * .75), max(120, natural)))
            else:
                bubble.setMaximumWidth(round(available * .95))
            bubble.browser.fit_height()

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
            self.follow_bottom = True
            for row in self.rows.values():
                self.box.removeWidget(row)
                row.hide()
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
                bubble.retry_requested.connect(self.retry_requested)
                if entry['role'] == 'user':
                    layout.addStretch(1)
                layout.addWidget(bubble, 0 if entry['role'] == 'user' else 1)
                self.box.insertWidget(self.box.count() - 1, row)
                self.bubbles[entry['id']] = bubble
                self.rows[entry['id']] = row
            else:
                bubble.update_entry(entry)
        messages = data['messages'] if data else []
        latest = next((entry['id'] for entry in reversed(messages) if entry['role'] == 'assistant'), None)
        for message_id, bubble in self.bubbles.items():
            bubble.retry_button.setVisible(message_id == latest)
            bubble.retry_button.setEnabled(self.retry_enabled)
        valid = {entry['id'] for entry in data['messages']} if data else set()
        for key in list(self.rows):
            if key not in valid:
                self.box.removeWidget(self.rows[key])
                row = self.rows.pop(key)
                row.hide()
                row.deleteLater()
                self.bubbles.pop(key)
        self._fit_bubbles()

    def set_retry_enabled(self, enabled):
        self.retry_enabled = enabled
        for bubble in self.bubbles.values():
            bubble.retry_button.setEnabled(enabled)

    def clear(self):
        self.sync(None)
