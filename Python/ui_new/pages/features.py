"""Session feature controls with dependency-aware enable/disable behavior."""
from commonUtils.ui import pyside as qt
from features import registry


class FeaturesPage(qt.QWidget):
    def __init__(self, parent=None, *, scope=None):
        super().__init__(parent)
        self.scope = scope or 'personal'
        self.controlled_scope = scope is not None
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
        self.path_label = qt.QLabel()
        self.path_label.setAccessibleName('Feature configuration file')
        self.path_label.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        content_layout.addWidget(self.path_label)
        self.description = qt.QLabel()
        self.description.setWordWrap(True)
        content_layout.addWidget(self.description)
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
        from commonUtils.ui.settings.settings_sections import ScopedSettings, SettingsSection
        self.sections = ScopedSettings(self)
        self.sections.set_sections([SettingsSection('personal', 'features', 'Features', self.scroll)])
        if self.controlled_scope:
            self.sections.tabs.tabBar().hide()
        layout.addWidget(self.sections)
        self.toggles = {}
        self.reset_buttons = {}
        self.states = {}
        self._unsubscribe = registry.subscribe(self._features_changed)
        self.destroyed.connect(self._unsubscribe)
        self.refresh()

    def set_scope(self, scope):
        self.scope = scope
        self.controlled_scope = True
        self.sections.tabs.tabBar().hide()
        self.refresh()

    def _features_changed(self):
        qt.QTimer.singleShot(0, self.refresh)

    def refresh(self):
        self.path_label.setText(str(registry.feature_settings_store().path(self.scope)))
        self.path_label.setToolTip('Repository defaults shipped in releases' if self.scope == 'application'
                                   else 'Personal feature choices override the shipped defaults')
        self.description.setText(
            'Default feature selection shipped with Logistics. Changes save immediately and affect future launches; '
            'personal settings can override them. Dependencies are enabled together.'
            if self.scope == 'application' else
            'Your personal feature selection overrides the shipped defaults and applies immediately. '
            'Changes save automatically. Dependencies are enabled together.')
        while self.cards.count():
            widget = self.cards.takeAt(0).widget()
            widget.hide(); widget.deleteLater()
        self.toggles.clear(); self.states.clear()
        self.reset_buttons.clear()
        defaults = registry.default_disabled_features()
        states = sorted(registry.get_feature_states(), key=lambda state: state.label.casefold())
        labels = {state.name: state.label for state in states}
        for state in states:
            error = getattr(state, 'error', '')
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
            members = getattr(state, 'members', ()) or (state.name,)
            default_enabled = all(member not in defaults for member in members)
            enabled = default_enabled if self.scope == 'application' else state.enabled
            toggle.setChecked(enabled)
            toggle.setEnabled(state.available)
            toggle.setToolTip((error or 'Required feature packages are missing.') if not state.available else
                              'Enable or disable this feature and remember the choice.')
            toggle.toggled.connect(lambda enabled, feature=state: self._toggled(feature, enabled))
            header.addWidget(toggle, 1)
            reset = qt.QToolButton()
            reset.setText('↶')
            reset.setAccessibleName(f'Reset {state.label} to default')
            reset.setToolTip('Restore enabled software baseline' if self.scope == 'application' else 'Use software default')
            reset.setEnabled(not enabled if self.scope == 'application' else enabled != default_enabled)
            reset.clicked.connect(lambda checked=False, feature=state, value=default_enabled:
                                  self._toggled(feature, True if self.scope == 'application' else value))
            header.addWidget(reset)
            text = ('Unavailable' if error else 'Missing dependency') if not state.available else 'Enabled' if enabled else 'Disabled'
            status = qt.QLabel(text)
            self._muted(status)
            header.addWidget(status)
            card_layout.addLayout(header)
            details = [error] if error else []
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
            self.reset_buttons[state.name] = reset
            self.states[state.name] = status

    @staticmethod
    def _muted(label):
        label.setForegroundRole(qt.QPalette.ColorRole.PlaceholderText)

    def _toggled(self, state, enabled):
        try:
            if self.scope == 'application':
                registry.set_feature_default(state.name, enabled)
            else:
                registry.set_feature_enabled(state.name, enabled)
        except Exception as error:
            self.status.setText(str(error))
            # Retain the emitting checkbox until Qt finishes delivering its signal.
            self._features_changed()
        else:
            self.status.setText(f'{state.label} {"enabled" if enabled else "disabled"}. Choice saved for the next launch.')

    def _reset_defaults(self):
        try:
            if self.scope == 'application':
                registry.feature_settings_store().save({('FeatureDefaults', 'disabled_list-str'): '[]'}, scope='application')
                self.refresh()
            else:
                registry.reset_feature_defaults()
        except Exception as error:
            self.status.setText(str(error))
            self._features_changed()
        else:
            self.status.setText('Defaults restored.')
