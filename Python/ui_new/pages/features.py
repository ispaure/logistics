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
        self.scope_label = qt.QLabel()
        font = self.scope_label.font(); font.setBold(True)
        self.scope_label.setFont(font)
        content_layout.addWidget(self.scope_label)
        self.path_label = qt.QLabel()
        self.path_label.setAccessibleName('Feature configuration file')
        self.path_label.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        content_layout.addWidget(self.path_label)
        self.description = qt.QLabel()
        self.description.setWordWrap(True)
        content_layout.addWidget(self.description)
        self.reset_all = qt.QPushButton('Reset to defaults')
        self.reset_all.clicked.connect(self._reset_defaults)
        content_layout.addWidget(self.reset_all, alignment=qt.Qt.AlignmentFlag.AlignRight)
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
        self.indicators = {}
        self.notes = {}
        self.summaries = {}
        self._card_widgets = {}
        self._feature_states = {}
        self._default_enabled = {}
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
        store = registry.feature_settings_store()
        personal = self.scope == 'personal'
        selection_override = ('FeatureDefaults', 'disabled_list-str') in store.overrides() if personal else False
        source = 'Override' if selection_override else 'Inherited'
        self.scope_label.setText(f'Personal overrides · {source} feature selection' if personal else 'Software defaults')
        self.path_label.setText(str(store.path(self.scope)))
        self.path_label.setToolTip('Repository defaults shipped in releases' if not personal
                                   else 'Personal feature choices override the shipped defaults')
        self.description.setText(
            'Default feature selection shipped with Logistics. Changes save immediately and affect future launches; '
            'personal settings can override them. Dependencies are enabled together.'
            if not personal else
            'Inherited selection uses software defaults. Toggling a feature saves the entire selection as a personal '
            'override and applies immediately. ↶ matches one feature to its software default; '
            'Use software defaults removes the selection override. Dependencies are enabled together.')
        self.reset_all.setText('Use software defaults' if personal else 'Reset to defaults')
        self.reset_all.setEnabled(selection_override if personal else bool(registry.default_disabled_features()))
        defaults = registry.default_disabled_features()
        states = sorted(registry.get_feature_states(), key=lambda state: state.label.casefold())
        self._feature_states = {state.name: state for state in states}
        labels = {state.name: state.label for state in states}
        # Preserve the controls, focus and scroll range across runtime notifications.
        for name in set(self._card_widgets) - self._feature_states.keys():
            card = self._card_widgets.pop(name)
            self.cards.removeWidget(card)
            card.hide(); card.deleteLater()
            for mapping in (self.toggles, self.reset_buttons, self.states, self.indicators,
                            self.notes, self.summaries, self._default_enabled):
                mapping.pop(name, None)
        for index, state in enumerate(states):
            if state.name not in self._card_widgets:
                self._add_card(state.name, index)
            error = getattr(state, 'error', '')
            members = getattr(state, 'members', ()) or (state.name,)
            default_enabled = all(member not in defaults for member in members)
            self._default_enabled[state.name] = default_enabled
            enabled = state.enabled if personal else default_enabled
            toggle = self.toggles[state.name]
            toggle.setText(state.label)
            toggle.setAccessibleName(f'Enable {state.label}')
            with qt.QSignalBlocker(toggle):
                toggle.setChecked(enabled)
            toggle.setEnabled(state.available)
            toggle.setToolTip((error or 'Required feature packages are missing.') if not state.available else
                              'Enable or disable this feature and remember the choice.')
            reset = self.reset_buttons[state.name]
            reset.setAccessibleName(f'Reset {state.label} to default')
            reset.setToolTip('Use software default' if personal else 'Restore enabled software baseline')
            reset.setEnabled(enabled != default_enabled if personal else not enabled)
            indicator = self.indicators[state.name]
            indicator.setText(source if personal else '')
            indicator.setVisible(personal)
            indicator.setToolTip(
                ('The entire feature selection is saved as a personal override. ' if selection_override
                 else 'The feature selection is inherited from software defaults. ')
                + ('This feature matches its software default.' if enabled == default_enabled
                   else 'This feature differs from its software default.'))
            text = ('Unavailable' if error else 'Missing dependency') if not state.available else 'Enabled' if enabled else 'Disabled'
            self.states[state.name].setText(text)
            summary = self.summaries[state.name]
            summary.setText(getattr(state, 'description', ''))
            summary.setVisible(bool(summary.text()))
            details = [error] if error else []
            if state.dependencies:
                details.append('Requires: ' + ', '.join(labels.get(name, name) for name in state.dependencies))
            if state.dependents:
                details.append('Used by: ' + ', '.join(labels.get(name, name) for name in state.dependents))
            note = self.notes[state.name]
            note.setText(' · '.join(details))
            note.setVisible(bool(details))

    def _add_card(self, name, index):
        card = qt.QFrame()
        card.setObjectName('featureCard')
        card.setStyleSheet('QFrame#featureCard { background: palette(base); border: 1px solid palette(mid); border-radius: 6px; }')
        card.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Maximum)
        card_layout = qt.QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        header = qt.QHBoxLayout()
        toggle = self.toggles[name] = qt.QCheckBox()
        font = toggle.font(); font.setBold(True); toggle.setFont(font)
        toggle.toggled.connect(lambda enabled, name=name: self._toggled(self._feature_states[name], enabled))
        header.addWidget(toggle, 1)
        status = self.states[name] = qt.QLabel()
        self._muted(status)
        header.addWidget(status)
        indicator = self.indicators[name] = qt.QLabel()
        indicator.setMinimumWidth(65)
        header.addWidget(indicator)
        reset = self.reset_buttons[name] = qt.QToolButton()
        reset.setText('↶')
        reset.clicked.connect(lambda checked=False, name=name: self._toggled(
            self._feature_states[name], self._default_enabled[name] if self.scope == 'personal' else True))
        header.addWidget(reset)
        card_layout.addLayout(header)
        summary = self.summaries[name] = qt.QLabel()
        summary.setWordWrap(True)
        summary.setTextFormat(qt.Qt.TextFormat.PlainText)
        self._muted(summary)
        card_layout.addWidget(summary)
        note = self.notes[name] = qt.QLabel()
        note.setWordWrap(True)
        note.setTextFormat(qt.Qt.TextFormat.PlainText)
        self._muted(note)
        card_layout.addWidget(note)
        self._card_widgets[name] = card
        self.cards.insertWidget(index, card)

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
