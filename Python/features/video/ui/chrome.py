"""Docked video chrome: header, bounded picture, adjacent settings and control deck."""
from pathlib import Path

from commonUtils.ui import pyside as qt
from commonUtils.ui.readers.reader_chrome import ReaderFullscreen, ReaderLabel, reader_button
from .controls import CachedSlider
from .icons import video_button


class DockedChrome:
    def build_chrome(self):
        self.backend = self.backend_factory(self)
        self.player, self.audio = self.backend.player, self.backend.audio
        body = qt.QWidget()
        self.setCentralWidget(body)
        outer = qt.QVBoxLayout(body)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = qt.QWidget()
        self.header_layout = qt.QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(12, 8, 12, 8)
        self.header_layout.setSpacing(4)
        identity = qt.QWidget()
        identity.setMinimumWidth(0)
        identity.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Preferred)
        title = qt.QVBoxLayout(identity)
        title.setContentsMargins(0, 0, 0, 0)
        title.setSpacing(0)
        self.identity = ReaderLabel(Path(self.content.path).name)
        self.identity.setAccessibleName('Video filename')
        font = self.identity.font()
        font.setBold(True)
        self.identity.setFont(font)
        from services.documents.storage import document_sources
        private = any(getattr(source, 'private', False) for source in document_sources(self.content.provider))
        source = 'Cloud file' if self.content.remote else 'Local encrypted file' if private else 'Local file'
        self.source_label = ReaderLabel(source, muted=True)
        self.source_label.setAccessibleName('Video source')
        title.addWidget(self.identity)
        title.addWidget(self.source_label)
        self.header_layout.addWidget(identity, 1)
        self.favourite_button = self.button('Favourite file', 'star', self.favourite_file)
        self.folder_button = self.button('Show in folder', 'folder', self.show_in_folder)
        self.floating = self.button('Floating window', 'floating', self.toggle_floating)
        self.floating.setCheckable(True)
        self.header_buttons = [self.favourite_button, self.folder_button, self.floating]
        if self.backend.capabilities.receivers:
            self.cast_button = self.button('Cast…', 'cast', self.show_receivers)
            self.header_buttons.append(self.cast_button)
        restricted = self.content.restricted or self.process_contexts
        for button in self.header_buttons:
            self.header_layout.addWidget(button)
        for button in (self.floating, getattr(self, 'cast_button', None)):
            if button is not None:
                button.setEnabled(not restricted)
                if restricted:
                    button.setToolTip('Unavailable while session-only credentials protect playback.')
        outer.addWidget(self.header)

        self.middle = qt.QWidget()
        self.middle_layout = qt.QBoxLayout(qt.QBoxLayout.Direction.LeftToRight, self.middle)
        self.middle_layout.setContentsMargins(0, 0, 0, 0)
        self.middle_layout.setSpacing(0)
        self.stage = qt.QWidget()
        self.stage.setMinimumSize(0, 48)
        layers = qt.QStackedLayout(self.stage)
        layers.setContentsMargins(0, 0, 0, 0)
        layers.setStackingMode(qt.QStackedLayout.StackingMode.StackAll)
        self.video = self.backend.video
        self.video_viewport = qt.QScrollArea()
        self.video_viewport.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.video_viewport.setMinimumSize(0, 0)
        self.video_viewport.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.video_viewport.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.video_viewport.setVerticalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.video_viewport.setStyleSheet('background: black;')
        self.video_viewport.setWidget(self.video)
        layers.addWidget(self.video_viewport)
        self.overlay = qt.QWidget()
        captions = qt.QVBoxLayout(self.overlay)
        captions.setContentsMargins(12, 12, 12, 12)
        captions.addStretch(1)
        self.caption = qt.QLabel()
        self.caption.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.caption.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        self.caption.setMinimumWidth(0)
        captions.addWidget(self.caption)
        self.caption.hide()
        layers.addWidget(self.overlay)
        layers.setCurrentWidget(self.overlay)
        self.middle_layout.addWidget(self.stage, 1)
        self.build_settings_pane()
        self.middle_layout.addWidget(self.settings_pane)
        outer.addWidget(self.middle, 1)

        # Retain the deck/header allocations during full-screen hiding and lock.
        self.dock = qt.QWidget()
        deck = qt.QStackedLayout(self.dock)
        deck.setStackingMode(qt.QStackedLayout.StackingMode.StackAll)
        deck.setContentsMargins(0, 0, 0, 0)
        deck.setSpacing(0)
        self.chrome = qt.QWidget()
        self.chrome.setAutoFillBackground(True)
        layout = qt.QVBoxLayout(self.chrome)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(2)
        self.time = qt.QLabel('0:00:00 / Loading duration…')
        self.time.setAccessibleName('Elapsed and total time')
        layout.addWidget(self.time)
        self.seek = CachedSlider(qt.Qt.Orientation.Horizontal)
        self.seek.setMinimumWidth(0)
        self.seek.setAccessibleName('Video position')
        self.seek.sliderReleased.connect(lambda: self.seek_to(self.seek.value()))
        layout.addWidget(self.seek)
        self.control_rows = qt.QGridLayout()
        self.control_rows.setContentsMargins(0, 0, 0, 0)
        self.control_rows.setSpacing(2)
        self.transport_controls = qt.QWidget()
        transport = qt.QHBoxLayout(self.transport_controls)
        transport.setContentsMargins(0, 0, 0, 0)
        transport.setSpacing(0)
        self.previous_video = self.button('Previous video (P)', 'previous-file', lambda: self.queue_move(-1))
        self.backward = self.button('Back 10 seconds (Left)', 'back10', lambda: self.skip(-10000))
        self.play = self.button('Play', 'play', self.toggle_play)
        self.play.setToolTip('Play (Space)')
        self.play.setMinimumSize(42, 42)
        self.forward = self.button('Forward 10 seconds (Right)', 'forward10', lambda: self.skip(10000))
        self.next_video = self.button('Next video (N)', 'next-file', lambda: self.queue_move(1))
        self.mute = self.button('Mute', 'speaker', lambda: self.audio.setMuted(not self.audio.isMuted()))
        self.mute.setCheckable(True)
        self.mute.setToolTip('Mute (M)')
        self.audio.mutedChanged.connect(self.update_mute)
        for button in (self.previous_video, self.backward, self.play, self.forward, self.next_video, self.mute):
            transport.addWidget(button)
        self.volume = qt.QSlider(qt.Qt.Orientation.Horizontal)
        self.volume.setAccessibleName('Volume')
        self.volume.setRange(0, 100)
        self.volume.setValue(round(self.audio.volume() * 100))
        self.volume.setFixedWidth(70)
        self.volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        transport.addWidget(self.volume)
        transport.addStretch(1)
        self.utility_controls = qt.QWidget()
        utilities = qt.QHBoxLayout(self.utility_controls)
        utilities.setContentsMargins(0, 0, 0, 0)
        utilities.setSpacing(0)
        self.speed_button = self.button('Playback speed', None, lambda: self.show_settings('speed'))
        self.speed_button.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.picture_button = self.button('Picture size', 'picture', lambda: self.show_settings('picture'))
        self.audio_button = self.button('Audio tracks and sync', 'audio', lambda: self.show_settings('audio'))
        self.subtitle_button = self.button('Subtitles', 'captions', lambda: self.show_settings('subtitles'))
        self.chapters = self.button('Chapters', 'chapters', self.show_chapters)
        self.chapter_result.connect(self.chapters_loaded)
        self.queue_button = self.button('Current folder', 'queue', lambda: self.show_settings('queue'))
        self.tools_button = self.button('Playback tools', 'more', self.show_tools)
        self.fullscreen_action = qt.QAction('Full screen', self)
        self.fullscreen_action.setCheckable(True)
        self.fullscreen = ReaderFullscreen(self, self.fullscreen_action)
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.fullscreen_button = reader_button(self, 'Full screen', action=self.fullscreen_action, icon='fullscreen')
        self.fullscreen_button.setMinimumSize(36, 36)
        self.utility_buttons = (self.speed_button, self.picture_button, self.audio_button, self.subtitle_button,
                                self.chapters, self.queue_button, self.tools_button, self.fullscreen_button)
        for button in self.utility_buttons:
            utilities.addWidget(button)
        self.control_rows.addWidget(self.transport_controls, 0, 0)
        self.control_rows.addWidget(self.utility_controls, 0, 1)
        self.control_rows.setColumnStretch(0, 1)
        layout.addLayout(self.control_rows)
        feedback = qt.QHBoxLayout()
        self.status = ReaderLabel('Ready. Press Play to start.', muted=True)
        self.status.setAccessibleName('Playback status')
        feedback.addWidget(self.status, 1)
        self.undo_button = qt.QPushButton('Undo seek')
        self.undo_button.clicked.connect(self.undo_seek)
        self.undo_button.hide()
        feedback.addWidget(self.undo_button)
        self.cache_label = qt.QLabel('Cache ≈' if self.content.remote else 'Local file')
        self.cache_label.setToolTip('Approximate cached byte ranges mapped to time.' if self.content.remote else 'Available locally.')
        feedback.addWidget(self.cache_label)
        layout.addLayout(feedback)
        # Loading/error feedback lives in the deck, never over the picture.
        self.wait_indicator = qt.QLabel('Buffering…')
        self.wait_indicator.setAccessibleName('Waiting for video data')
        feedback.insertWidget(0, self.wait_indicator)
        self.wait_indicator.hide()
        deck.addWidget(self.chrome)
        self.unlock_button = qt.QPushButton('Unlock controls (Escape)')
        self.unlock_container = qt.QWidget()
        unlock_layout = qt.QVBoxLayout(self.unlock_container)
        unlock_layout.addWidget(self.unlock_button, 0, qt.Qt.AlignmentFlag.AlignCenter)
        deck.addWidget(self.unlock_container)
        self.unlock_container.hide()
        outer.addWidget(self.dock)
        for widget in (self.chrome, self.header, self.identity):
            policy = widget.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            widget.setSizePolicy(policy)
        self.action_buttons = self.utility_buttons
        self.setMinimumSize(320, 280)
        self.reflow_chrome()

    def button(self, label, icon, callback):
        return video_button(self, label, icon, callback)

    def reflow_chrome(self):
        if not hasattr(self, 'utility_controls'):
            return
        width = self.centralWidget().width()
        short_panel = width < 760 and self.height() < 400 and self.panel_name is not None
        self.utility_controls.setVisible(not short_panel)
        self.panel_selector.setVisible(short_panel)
        self.panel_title.setVisible(not short_panel)
        self.volume.setVisible(width >= 420)
        needed = self.transport_controls.sizeHint().width() + self.utility_controls.sizeHint().width() + 28
        stacked = width < needed
        self.control_rows.removeWidget(self.utility_controls)
        self.control_rows.addWidget(self.utility_controls, int(stacked), 0 if stacked else 1,
                                    qt.Qt.AlignmentFlag.AlignRight)
        self.control_rows.setColumnStretch(1, 0)
        self.chrome.layout().activate()
        deck_height = self.chrome.minimumSizeHint().height()
        self.dock.setMinimumHeight(deck_height)
        narrow = width < 760
        self.middle_layout.setDirection(qt.QBoxLayout.Direction.TopToBottom if narrow else qt.QBoxLayout.Direction.LeftToRight)
        self.settings_pane.setMinimumWidth(0 if narrow else 250)
        self.settings_pane.setMaximumWidth(16777215 if narrow else 290)
        available = self.height() - self.header.minimumSizeHint().height() - deck_height - self.stage.minimumHeight()
        self.settings_pane.setMaximumHeight(max(48, min(210, self.height() // 3, available)) if narrow else 16777215)

    def favourite_file(self):
        if not self.controls_allowed():
            return
        try:
            from services.documents.ui.editors import favourite_document
            favourite_document(self)
            self.status.setText('Added to favourites.')
        except (OSError, ValueError, PermissionError) as error:
            self.status.setText(str(error))
