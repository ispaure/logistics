"""Incremental conversation bubbles with native, selectable Markdown bodies."""
from commonUtils.ui.appearance.typography import point_size
import math
from datetime import datetime
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.styling import styling
from commonUtils.ui.markdown.presentation import ACCENT, MarkdownBrowser, style_document, monospace_family, code_point_size, blend
from .image_view import ScreenshotView
from .changes import EditedFilesCard
from .icons import action_button, chat_icon
from .user_message import set_user_document


def message_palette(user=False):
    palette = qt.QPalette(qt.QApplication.palette())
    role = qt.QPalette.ColorRole
    if user:
        accent = palette.color(role.Link)
        channels = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                    for value in accent.getRgbF()[:3]]
        luminance = sum(value * weight for value, weight in zip(channels, (.2126, .7152, .0722)))
        text = qt.QColor('#000000' if luminance > .179 else '#ffffff')
        for key, color in ((role.Base, accent), (role.Window, accent),
                           (role.Text, text), (role.WindowText, text),
                           (role.PlaceholderText, blend(accent, text, .8))):
            palette.setColor(key, color)
    return palette


class MessageBrowser(MarkdownBrowser):
    def __init__(self, parent=None, *, literal_prose=False):
        super().__init__(parent)
        self.literal_prose = literal_prose
        self.source = None
        self._appearance = None
        self.code_buttons = []
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setVerticalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Fixed)
        self.horizontalScrollBar().valueChanged.connect(self.position_code_buttons)
        self.verticalScrollBar().valueChanged.connect(self.position_code_buttons)
        styling().changed.connect(self.refresh_font)
        theme = getattr(qt.QApplication.instance(), '_commonutils_theme', None)
        if theme is not None:
            theme.changed.connect(self.refresh_font)
        self.refresh_font()

    def loadResource(self, kind, url):
        return qt.QByteArray()

    def refresh_font(self):
        font = styling().font('reading')
        appearance = (font.key(), monospace_family(), code_point_size(), qt.QApplication.palette().cacheKey())
        if appearance == self._appearance:
            return
        self._appearance = appearance
        palette = message_palette(self.literal_prose)
        self.setPalette(palette)
        family = font.family().replace('\\', '\\\\').replace('"', '\\"')
        stylesheet = f'QTextBrowser {{ background: transparent; border: none; color: {palette.color(qt.QPalette.ColorRole.Text).name()}; font-family: "{family}"; font-size: {font.pointSizeF()}pt; }}'
        if self.styleSheet() != stylesheet:
            self.setStyleSheet(stylesheet)
        if self.document().defaultFont() != font:
            self.document().setDefaultFont(font)
        if self.source is not None:
            self.set_source(self.source, force=True)

    def set_source(self, source, *, force=False):
        if source == self.source and not force:
            return
        self.source = source
        cursor = self.textCursor()
        position, anchor = cursor.position(), cursor.anchor()
        # Discard controls before Qt replaces frames and emits layout/scroll signals.
        for frame, button in self.code_buttons:
            button.hide()
            button.deleteLater()
        self.code_buttons.clear()
        if self.literal_prose:
            set_user_document(self.document(), source)
        else:
            self.document().setMarkdown(source, qt.QTextDocument.MarkdownFeature.MarkdownDialectGitHub |
                                        qt.QTextDocument.MarkdownFeature.MarkdownNoHTML)
        style_document(self.document(), message_palette(self.literal_prose), callouts={})
        self.document().setDocumentMargin(8)
        self.rebuild_code_buttons()
        cursor = qt.QTextCursor(self.document())
        end = self.document().characterCount() - 1
        cursor.setPosition(min(anchor, end))
        cursor.setPosition(min(position, end), qt.QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        self.fit_height()

    def rebuild_code_buttons(self):
        def visit(parent):
            for frame in parent.childFrames():
                # Reading frames are code panels, accent-marked quotes or tables.
                # Qt clears the original code-block flags when inserting frames.
                if not isinstance(frame, qt.QTextTable) and not frame.format().hasProperty(ACCENT):
                    button = action_button('Copy code', lambda checked=False, frame=frame: self.copy_code(frame),
                                           'copy', size=16, parent=self.viewport())
                    button.setIcon(chat_icon('copy', message_palette(self.literal_prose).color(qt.QPalette.ColorRole.Text)))
                    button.setAutoRaise(False)
                    button.adjustSize()
                    self.code_buttons.append((frame, button))
                    # Reserve a header row even for code without a language label.
                    fmt = frame.frameFormat()
                    palette = message_palette(self.literal_prose)
                    fmt.setBackground(blend(palette.color(qt.QPalette.ColorRole.Base),
                                            palette.color(qt.QPalette.ColorRole.Text), .08))
                    fmt.setPadding(max(fmt.padding(), button.height() + 4))
                    frame.setFrameFormat(fmt)
                    button.show()
                visit(frame)

        visit(self.document().rootFrame())

    def copy_code(self, frame):
        cursor = qt.QTextCursor(self.document())
        cursor.setPosition(frame.firstPosition())
        cursor.setPosition(frame.lastPosition(), qt.QTextCursor.MoveMode.KeepAnchor)
        qt.QApplication.clipboard().setText(cursor.selectedText().replace('\u2029', '\n'))

    def position_code_buttons(self):
        layout = self.document().documentLayout()
        for frame, button in self.code_buttons:
            rect = layout.frameBoundingRect(frame).translated(-self.horizontalScrollBar().value(),
                                                             -self.verticalScrollBar().value())
            right = min(rect.right(), self.viewport().width())
            button.move(round(right - button.width() - 6), round(rect.top() + 6))

    def fit_height(self):
        self.document().setTextWidth(max(80, self.viewport().width()))
        height = math.ceil(self.document().size().height()) + 4
        if self.horizontalScrollBar().isVisible():
            height += self.horizontalScrollBar().height()
        if self.height() != height:
            self.setFixedHeight(height)
        self.position_code_buttons()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_height()


class Bubble(qt.QFrame):
    speak_requested = qt.Signal()
    retry_requested = qt.Signal()
    changes_requested = qt.Signal(str, str)
    undo_requested = qt.Signal(str)
    edit_requested = qt.Signal(str, str)

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
        self.label.setVisible(self.role == 'user')
        self.work_button = qt.QToolButton()
        self.work_button.setAutoRaise(True)
        self.work_button.setCheckable(True)
        self.work_button.setVisible(self.role == 'assistant')
        self.work_button.setAccessibleName('Response activity and server reasoning')
        header.addWidget(self.work_button)
        header.addStretch()
        self.copy_button = action_button('Copy message as written',
            lambda: qt.QApplication.clipboard().setText(self.browser.source or ''), 'copy', size=16)
        self.browser = MessageBrowser(self, literal_prose=self.role == 'user')
        self.error = qt.QLabel()
        self.error.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        self.error.setForegroundRole(qt.QPalette.ColorRole.PlaceholderText)
        layout.addLayout(header)
        self.reasoning_browser = None
        self.reasoning_manual = False
        if self.role == 'assistant':
            self.reasoning_browser = MessageBrowser(self)
            self.reasoning_browser.setAccessibleName('Reasoning returned by the server')
            self.reasoning_browser.hide()
            self.work_button.toggled.connect(self.reasoning_browser.setVisible)
            self.work_button.toggled.connect(lambda checked: self.update_activity())
            self.work_button.clicked.connect(lambda: setattr(self, 'reasoning_manual', True))
            layout.addWidget(self.reasoning_browser)
            separator = qt.QFrame()
            separator.setFixedHeight(1)
            separator.setStyleSheet('background: palette(mid); border: none;')
            layout.addWidget(separator)
        layout.addWidget(self.browser)
        self.images_box = qt.QWidget()
        self.images_layout = qt.QVBoxLayout(self.images_box)
        self.images_layout.setContentsMargins(0, 0, 0, 0)
        self.image_ids = None
        self.images = []
        layout.addWidget(self.images_box)
        layout.addWidget(self.error)
        self.changes_card = EditedFilesCard(self)
        self.changes_card.file_requested.connect(lambda path: self.changes_requested.emit(entry['id'], path))
        self.changes_card.edit_requested.connect(lambda path: self.edit_requested.emit(entry['id'], path))
        self.changes_card.undo_requested.connect(lambda: self.undo_requested.emit(entry['id']))
        layout.addWidget(self.changes_card)
        footer = qt.QHBoxLayout()
        footer.setSpacing(4)
        footer.addWidget(self.copy_button)
        self.copy_button.setVisible(self.role != 'user')
        self.speak_button = action_button('Read answer aloud', self.speak_requested, 'speaker', size=16)
        self.speak_button.setCheckable(True)
        self.speak_button.setVisible(self.role == 'assistant')
        footer.addWidget(self.speak_button)
        self.retry_button = action_button('Retry / Regenerate last response', self.retry_requested, 'refresh', size=16)
        self.retry_button.hide()
        footer.addWidget(self.retry_button)
        if self.role == 'user':
            footer.addStretch()
        self.timestamp = qt.QLabel()
        self.timestamp.setTextFormat(qt.Qt.TextFormat.PlainText)
        footer.addWidget(self.timestamp)
        if self.role != 'user':
            footer.addStretch()
        layout.addLayout(footer)
        styling().changed.connect(self.refresh_chrome)
        theme = getattr(qt.QApplication.instance(), '_commonutils_theme', None)
        if theme is not None:
            theme.changed.connect(self.refresh_chrome)
        self.update_entry(entry)
        self.work_timer = qt.QTimer(self)
        self.work_timer.setInterval(1000)
        self.work_timer.timeout.connect(self.update_activity)
        if self.role == 'assistant' and entry['status'] == 'streaming':
            self.work_timer.start()

    def update_activity(self):
        entry = self._entry
        if self.role != 'assistant':
            return
        elapsed = entry.get('elapsed_seconds')
        if entry['status'] == 'streaming':
            try:
                created = datetime.fromisoformat(entry.get('created', '')).astimezone()
                elapsed = max(0, (datetime.now().astimezone() - created).total_seconds())
            except (ValueError, TypeError):
                elapsed = 0
        if elapsed is None:
            text = 'Response' if entry['status'] == 'complete' else entry['status'].capitalize()
        else:
            minutes, seconds = divmod(int(elapsed), 60)
            duration = f'{minutes}m {seconds}s' if minutes else f'{seconds}s'
            prefix = {'streaming': 'Working ·', 'complete': 'Worked for', 'cancelled': 'Stopped after',
                      'failed': 'Failed after', 'interrupted': 'Interrupted after'}[entry['status']]
            text = f'{prefix} {duration}'
        has_reasoning = bool(entry.get('reasoning'))
        self.work_button.setText(text + (' ⌄' if self.work_button.isChecked() else ' ›') if has_reasoning else text)
        self.work_button.setEnabled(has_reasoning)
        self.work_button.setToolTip('Show or hide reasoning returned by the server. Duration includes the whole response.'
                                   if has_reasoning else 'Total response time. This server returned no separate reasoning text.')

    def refresh_chrome(self):
        # Local stylesheets can retain the previous Base palette; always obtain
        # theme colors from the application, rather than sampling the bubble.
        palette = message_palette(self.role == 'user')
        self.setPalette(palette)
        muted = palette.color(qt.QPalette.ColorRole.PlaceholderText).name()
        stylesheet = f'color: {muted}; font-size: {point_size(6.75)}pt;'
        if self.timestamp.styleSheet() != stylesheet:
            self.timestamp.setStyleSheet(stylesheet)
        background = palette.color(qt.QPalette.ColorRole.Base).name()
        stylesheet = f'QFrame#userBubble {{ background: {background}; border-radius: 12px; }}'
        if self.role == 'user' and self.styleSheet() != stylesheet:
            self.setStyleSheet(stylesheet)
        self.label.setPalette(palette)

    def update_entry(self, entry):
        self._entry = entry
        self.speak_button.setEnabled(self.role == 'assistant' and entry['status'] != 'streaming' and bool(entry['content'].strip()))
        if self.reasoning_browser is not None:
            reasoning = entry.get('reasoning', '')
            self.reasoning_browser.set_source(reasoning)
            if not self.reasoning_manual:
                self.work_button.setChecked(bool(reasoning) and entry['status'] == 'streaming' and not entry['content'])
            self.reasoning_browser.setVisible(bool(reasoning) and self.work_button.isChecked())
            if hasattr(self, 'work_timer'):
                self.work_timer.start() if entry['status'] == 'streaming' else self.work_timer.stop()
        self.update_activity()
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
        self.changes_card.update_changes(entry.get('changes', []))
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
    speech_error = qt.Signal(str)
    retry_requested = qt.Signal()
    changes_requested = qt.Signal(str, str)
    undo_requested = qt.Signal(str)
    edit_requested = qt.Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.setObjectName('conversationPanel')
        self.setStyleSheet('QScrollArea#conversationPanel { background: palette(base); border: 1px solid palette(mid); border-radius: 8px; }')
        self.body = qt.QWidget()
        self.body.setBackgroundRole(qt.QPalette.ColorRole.Base)
        self.body.setAutoFillBackground(True)
        self.box = qt.QVBoxLayout(self.body)
        self.box.setContentsMargins(12, 8, 12, 8)
        self.box.setSpacing(12)
        self.box.addStretch()
        self.setWidget(self.body)
        self.viewport().setBackgroundRole(qt.QPalette.ColorRole.Base)
        self.bubbles = {}
        self.rows = {}
        self.key = None
        self.follow_bottom = True
        self.retry_enabled = False
        self.speech = None
        self.verticalScrollBar().rangeChanged.connect(self._range_changed)
        self.verticalScrollBar().valueChanged.connect(self._scrolled)
        styling().changed.connect(self._fit_bubbles)
        styling().changed.connect(self.refresh_surface)
        theme = getattr(qt.QApplication.instance(), '_commonutils_theme', None)
        if theme is not None:
            theme.changed.connect(self.refresh_surface)
        self.refresh_surface()

    def refresh_surface(self):
        palette = qt.QPalette(qt.QApplication.palette())
        self.body.setPalette(palette)
        self.viewport().setPalette(palette)

    def set_bottom_inset(self, height):
        height = max(8, height)
        if self.box.contentsMargins().bottom() != height:
            self.box.setContentsMargins(12, 8, 12, height)

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
            self.stop_speech()
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
                bubble.speak_requested.connect(lambda key=entry['id']: self.toggle_speech(key))
                bubble.retry_requested.connect(self.retry_requested)
                bubble.changes_requested.connect(self.changes_requested)
                bubble.edit_requested.connect(self.edit_requested)
                bubble.undo_requested.connect(self.undo_requested)
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
            bubble.changes_card.set_actions_enabled(self.retry_enabled)
        valid = {entry['id'] for entry in data['messages']} if data else set()
        if self.speech is not None and self.speech.active is not None and self.speech.active not in valid:
            self.stop_speech()
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
            bubble.changes_card.set_actions_enabled(enabled)

    def clear(self):
        self.sync(None)

    def toggle_speech(self, key):
        bubble = self.bubbles.get(key)
        if bubble is None or not bubble.speak_button.isEnabled():
            return
        if self.speech is None:
            from .answer_speech import AnswerSpeech
            self.speech = AnswerSpeech(self)
            self.speech.changed.connect(self.speech_changed)
            self.speech.error.connect(self.speech_error)
        # Read the rendered answer only, excluding Markdown delimiters and reasoning.
        self.speech.toggle(key, bubble.browser.document().toPlainText())

    def speech_changed(self, active):
        for key, bubble in self.bubbles.items():
            reading = key == active
            bubble.speak_button.setChecked(reading)
            bubble.speak_button.setIcon(chat_icon('speaker_stop' if reading else 'speaker'))
            label = 'Stop reading answer' if reading else 'Read answer aloud'
            bubble.speak_button.setToolTip(label)
            bubble.speak_button.setAccessibleName(label)

    def stop_speech(self):
        if self.speech is not None:
            self.speech.stop()
