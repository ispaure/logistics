"""Session feature controls with dependency-aware enable/disable behavior."""
from commonUtils.ui import pyside as qt
from features import registry


class FeaturesPage(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        self.scroll = qt.QScrollArea()
        self.scroll.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setAlignment(qt.Qt.AlignmentFlag.AlignHCenter | qt.Qt.AlignmentFlag.AlignTop)
        self.content = qt.QWidget()
        self.content.setMaximumWidth(820)
        content_layout = qt.QVBoxLayout(self.content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(16)
        title = qt.QLabel('Features')
        font = title.font(); font.setPointSize(font.pointSize() + 5); font.setBold(True)
        title.setFont(font)
        content_layout.addWidget(title)
        description = qt.QLabel('Choose which features to use. Required dependencies are enabled together. '
                                'Choices are saved for your next launch; existing windows and jobs can finish.')
        from features.preferences import preferences_path
        from ui_new.settings.storage import StorageNotice
        content_layout.addWidget(StorageNotice(preferences_path(), self, scope="personal"))
        description.setWordWrap(True)
        content_layout.addWidget(description)
        reset = qt.QPushButton('Reset to defaults')
        reset.clicked.connect(self._reset_defaults)
        content_layout.addWidget(reset, alignment=qt.Qt.AlignmentFlag.AlignRight)
        self.cards = qt.QVBoxLayout()
        self.cards.setSpacing(10)
        content_layout.addLayout(self.cards)
        self.status = qt.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        content_layout.addWidget(self.status)
        content_layout.addStretch()
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll)
        self.toggles = {}
        self.states = {}
        self._unsubscribe = registry.subscribe(self._features_changed)
        self.destroyed.connect(self._unsubscribe)
        self.refresh()

    def _features_changed(self):
        qt.QTimer.singleShot(0, self.refresh)

    def refresh(self):
        while self.cards.count():
            widget = self.cards.takeAt(0).widget()
            widget.hide(); widget.deleteLater()
        self.toggles.clear(); self.states.clear()
        states = sorted(registry.get_feature_states(), key=lambda state: state.label.casefold())
        labels = {state.name: state.label for state in states}
        for state in states:
            card = qt.QFrame()
            card.setObjectName('featureCard')
            card.setStyleSheet('QFrame#featureCard { background: palette(base); border: 1px solid palette(mid); border-radius: 6px; }')
            card.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Maximum)
            card_layout = qt.QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            header = qt.QHBoxLayout()
            toggle = qt.QCheckBox(state.label)
            toggle.setAccessibleName(f'Enable {state.label}')
            font = toggle.font(); font.setBold(True); toggle.setFont(font)
            toggle.setChecked(state.enabled)
            toggle.setEnabled(state.available)
            toggle.setToolTip('Required feature packages are missing.' if not state.available else
                              'Enable or disable this feature and remember the choice.')
            toggle.toggled.connect(lambda enabled, feature=state: self._toggled(feature, enabled))
            header.addWidget(toggle, 1)
            text = 'Missing dependency' if not state.available else 'Enabled' if state.enabled else 'Disabled'
            status = qt.QLabel(text)
            self._muted(status)
            header.addWidget(status)
            card_layout.addLayout(header)
            details = []
            if state.dependencies:
                details.append('Requires: ' + ', '.join(labels.get(name, name) for name in state.dependencies))
            if state.dependents:
                details.append('Used by: ' + ', '.join(labels.get(name, name) for name in state.dependents))
            if details:
                note = qt.QLabel(' · '.join(details))
                note.setWordWrap(True)
                self._muted(note)
                card_layout.addWidget(note)
            self.cards.addWidget(card)
            self.toggles[state.name] = toggle
            self.states[state.name] = status

    @staticmethod
    def _muted(label):
        label.setForegroundRole(qt.QPalette.ColorRole.PlaceholderText)

    def _toggled(self, state, enabled):
        try:
            registry.set_feature_enabled(state.name, enabled)
        except Exception as error:
            self.status.setText(str(error))
            # Retain the emitting checkbox until Qt finishes delivering its signal.
            self._features_changed()
        else:
            self.status.setText(f'{state.label} {"enabled" if enabled else "disabled"}. Choice saved for the next launch.')

    def _reset_defaults(self):
        try:
            registry.reset_feature_defaults()
        except Exception as error:
            self.status.setText(str(error))
            self._features_changed()
        else:
            self.status.setText('Defaults restored. All available features are enabled.')
