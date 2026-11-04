"""Scrollable, docked playback panels; all commands keep the video's access gate."""
from commonUtils.ui import pyside as qt
from features.video.session import RATES, ASPECTS, parse_time


class PlaybackPanels:
    def controls_allowed(self):
        if self.closing or getattr(self, 'controls_locked', False) or (
                self.resume_guard is not None and self.resume_guard.blocked):
            return False
        try:
            self.content.check_access()
            return True
        except (OSError, ValueError, PermissionError):
            return False

    def build_settings_pane(self):
        self.panel_name = None
        self.settings_pane = qt.QWidget()
        self.settings_pane.setMinimumSize(0, 0)
        layout = qt.QVBoxLayout(self.settings_pane)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)
        header = qt.QHBoxLayout()
        self.panel_title = qt.QLabel()
        header.addWidget(self.panel_title, 1)
        self.panel_selector = qt.QComboBox()
        self.panel_selector.setAccessibleName('Video settings category')
        self.panel_selector.setMinimumWidth(0)
        self.panel_selector.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Fixed)
        for key, title in (('playback', 'Playback'), ('speed', 'Speed'), ('picture', 'Picture'),
                           ('audio', 'Audio'), ('subtitles', 'Subtitles'), ('chapters', 'Chapters'), ('queue', 'Current folder')):
            self.panel_selector.addItem(title, key)
        if self.backend.capabilities.receivers:
            self.panel_selector.addItem('Cast', 'cast')
        self.panel_selector.activated.connect(lambda index: self.show_chapters()
            if self.panel_selector.itemData(index) == 'chapters' else self.show_receivers()
            if self.panel_selector.itemData(index) == 'cast' else self.show_settings(self.panel_selector.itemData(index)))
        header.addWidget(self.panel_selector, 1)
        self.panel_selector.hide()
        self.panel_close = self.button('Close settings', 'close', self.close_settings)
        header.addWidget(self.panel_close)
        layout.addLayout(header)
        self.settings_scroll = qt.QScrollArea()
        self.settings_scroll.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setMinimumSize(0, 0)
        self.settings_scroll.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.settings_scroll, 1)
        self.audio_tracks, self.subtitle_tracks = qt.QComboBox(self.settings_pane), qt.QComboBox(self.settings_pane)
        for combo, label in ((self.audio_tracks, 'Audio track'), (self.subtitle_tracks, 'Subtitles')):
            combo.setMinimumWidth(0)
            combo.setSizeAdjustPolicy(qt.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Fixed)
            combo.setAccessibleName(label)
            combo.hide()
        self.audio_tracks.activated.connect(self.select_audio)
        self.subtitle_tracks.activated.connect(self.select_subtitle)
        self.attach = qt.QPushButton('Choose subtitle file…', self.settings_pane)
        self.attach.clicked.connect(self.load_subtitles)
        self.attach.hide()
        self.settings_pane.hide()
        self.reflow_chrome()

    def select_audio(self, index):
        if self.controls_allowed():
            self.change_setting('audio_track', self.audio_tracks.itemData(index))

    def close_settings(self):
        for combo in self.settings_pane.findChildren(qt.QComboBox):
            combo.hidePopup()
        self.panel_name = None
        self.settings_pane.hide()
        self.reflow_chrome()
        for button in getattr(self, 'utility_buttons', ()):
            button.setChecked(False)
        self.overlay.setFocus()

    def show_settings(self, name):
        if not self.controls_allowed():
            return
        if self.panel_name == name and self.settings_pane.isVisible():
            self.close_settings()
            return
        self.panel_name = name
        self.fill_settings()
        self.settings_pane.show()
        self.reflow_chrome()
        self.show_controls()
        self.panel_close.setFocus()

    def fill_settings(self):
        name = self.panel_name
        titles = dict(playback='Playback', speed='Playback speed', picture='Picture', audio='Audio',
                      subtitles='Subtitles', chapters='Chapters', queue='Current folder', cast='Cast')
        self.panel_title.setText(titles[name])
        self.panel_selector.setCurrentIndex(self.panel_selector.findData(name))
        # Track widgets retain their selection across panels and metadata updates.
        for widget in (self.audio_tracks, self.subtitle_tracks, self.attach):
            widget.hide()
            widget.setParent(self.settings_pane)
        previous = self.settings_scroll.takeWidget()
        if previous is not None:
            previous.deleteLater()
        page = qt.QWidget()
        layout = qt.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        def note(text):
            label = qt.QLabel(text)
            label.setTextFormat(qt.Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            layout.addWidget(label)

        def action(text, callback):
            button = qt.QPushButton(text)
            button.setMinimumWidth(0)
            button.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Fixed)
            button.clicked.connect(callback)
            layout.addWidget(button)
            return button

        def choice(label, key, items):
            box = qt.QComboBox()
            box.setAccessibleName(label)
            box.setMinimumWidth(0)
            box.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Fixed)
            for title, value in items:
                box.addItem(title, value)
            box.setCurrentIndex(box.findData(getattr(self.settings, key)))
            box.activated.connect(lambda index: self.change_setting(key, box.itemData(index)))
            note(label)
            layout.addWidget(box)
            return box

        def delay(label, key):
            spin = qt.QSpinBox()
            spin.setAccessibleName(label)
            spin.setRange(-600000, 600000)
            spin.setSingleStep(50)
            spin.setSuffix(' ms')
            spin.setKeyboardTracking(False)
            spin.setValue(getattr(self.settings, key))
            spin.valueChanged.connect(lambda value: self.change_setting(key, value))
            note(label + ' · positive = later')
            layout.addWidget(spin)

        def language(label, key):
            edit = qt.QLineEdit(getattr(self.settings, key))
            edit.setAccessibleName(label)
            edit.setPlaceholderText('en, fr…; blank = default')
            edit.editingFinished.connect(lambda: self.change_setting(key, edit.text().strip()))
            note(label)
            layout.addWidget(edit)

        if name == 'speed':
            choice('Speed · pitch preserved', 'rate', [(f'{value:g}×', value) for value in RATES])
        elif name == 'picture':
            choice('Framing', 'aspect', [(dict(fit='Fit · whole picture', fill='Fill · crop edges',
                                              original='Original size')[value], value) for value in ASPECTS])
            hdr = action('HDR display mode · unavailable', lambda: None)
            hdr.setEnabled(False)
            note('This desktop decoder renders SDR frames. The iOS HDR brightness selector requires its native HDR display layer.')
        elif name == 'audio':
            note('Audio track')
            layout.addWidget(self.audio_tracks)
            self.audio_tracks.show()
            volume = qt.QSlider(qt.Qt.Orientation.Horizontal)
            volume.setRange(0, 100)
            volume.setValue(round(self.audio.volume() * 100))
            volume.setAccessibleName('Volume')
            volume.valueChanged.connect(self.volume.setValue)
            self.volume.valueChanged.connect(volume.setValue)
            note('Volume')
            layout.addWidget(volume)
            action('Mute / unmute (M)', self.mute.click)
            if self.backend.capabilities.audio_delay:
                delay('Audio delay', 'audio_delay_ms')
            else:
                note('Audio delay is unavailable with this decoder.')
            language('Preferred audio language', 'audio_language')
        elif name == 'subtitles':
            note('Subtitle track')
            layout.addWidget(self.subtitle_tracks)
            self.subtitle_tracks.show()
            layout.addWidget(self.attach)
            self.attach.show()
            scope = '' if self.backend.capabilities.embedded_subtitle_adjustment else 'External '
            choice(scope + 'subtitle size', 'subtitle_scale', [(f'{value:g}×', value) for value in (.75, 1., 1.25, 1.5, 2.)])
            delay(scope + 'subtitle delay', 'subtitle_delay_ms')
            language('Preferred subtitle language', 'subtitle_language')
            note('Embedded ASS styling can limit appearance overrides.' if not scope else
                 'Embedded subtitle appearance and delay are unavailable with this decoder.')
        elif name == 'playback':
            note('Go to time · seconds, MM:SS or HH:MM:SS')
            entry = qt.QLineEdit()
            entry.setAccessibleName('Go to time')
            layout.addWidget(entry)
            def go():
                try:
                    self.seek_to(parse_time(entry.text()))
                except ValueError as error:
                    self.status.setText(str(error))
            entry.returnPressed.connect(go)
            action('Go (G)', go)
            action('Start over', lambda: self.seek_to(0))
            action('Undo seek (Ctrl+Z)', self.undo_seek).setEnabled(self.undo_position is not None)
            action('Lock controls', lambda: self.lock_controls(True))
        elif name == 'queue':
            action('Previous video (P)', lambda: self.queue_move(-1))
            action('Next video (N)', lambda: self.queue_move(1))
            auto = qt.QCheckBox('Play next automatically')
            auto.setChecked(self.settings.autoplay_next)
            auto.toggled.connect(lambda value: self.change_setting('autoplay_next', value))
            layout.addWidget(auto)
            if self.queue is None:
                note('Loading folder…')
                self.load_queue()
            else:
                for row in self.queue.rows():
                    button = action(row['name'], lambda checked=False, path=row['path']: self.queue_open(path))
                    button.setToolTip(row['name'])
                    button.setCheckable(True)
                    button.setChecked(row['current'])
        elif name == 'chapters':
            if self.chapter_data is None:
                note('Loading chapters…')
            elif not self.chapter_data:
                note('This video has no supported embedded chapters.')
            else:
                from .player import clock
                for chapter in self.chapter_data:
                    action(f'{clock(chapter.start_ms)} · {chapter.title}',
                           lambda checked=False, position=chapter.start_ms: self.seek_to(position))
        elif name == 'cast':
            receivers = self.backend.receivers
            action('Return playback to this window', lambda: receivers.choose(self, None))
            for identity, label in receivers.rows():
                action(label, lambda checked=False, key=identity: receivers.choose(self, key))
            action('Refresh receivers', lambda: self.refresh_settings('cast'))
            note('Receiver discovery can take a few seconds. Refresh to update the list.')
        layout.addStretch(1)
        self.settings_scroll.setWidget(page)
        for button, panel in zip(getattr(self, 'utility_buttons', ()),
                                 ('speed', 'picture', 'audio', 'subtitles', 'chapters', 'queue', 'playback')):
            button.setCheckable(True)
            button.setChecked(name == panel)

    def refresh_settings(self, name):
        if self.panel_name == name and self.controls_allowed():
            self.fill_settings()
