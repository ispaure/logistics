"""Settings → Appearance & shared controls, including session theme and seasonal snow."""
from commonUtils.ui import pyside as qt
from commonUtils.configuration.settings import settings_path
from features.settings import settings_store
from .configuration import ConfigurationPanel


class AppearanceSettingsPanel(ConfigurationPanel):
    """The Appearance & shared controls category."""

    def __init__(self, parent=None, *, layered=False, scope='application'):
        super().__init__([settings_path()], parent, layered=layered, scope=scope, scoped=not layered)
        from desktop.snow import CONFIG, FIELD
        self._snow_store = settings_store(CONFIG)
        self.snow_choice = qt.QCheckBox('Seasonal snow')
        self.snow_choice.setToolTip('Snow from December 15 through January 2, inclusive. Disabled in high-contrast mode. Saved immediately.')
        self.snow_status = qt.QLabel()
        self.snow_status.setWordWrap(True)
        self.layout().insertWidget(0, self.snow_status)
        self.layout().insertWidget(0, self.snow_choice)
        self._snow_field = FIELD
        self._load_snow()
        self.snow_choice.toggled.connect(self._save_snow)
        if layered:
            return
        appearance = qt.QHBoxLayout()
        appearance.addWidget(qt.QLabel('Appearance (session)'))
        self.theme_mode = qt.QComboBox()
        self.theme_mode.setAccessibleName('Appearance mode')
        for label, mode in [('System', 'system'), ('Light', 'light'), ('Dark', 'dark')]:
            self.theme_mode.addItem(label, mode)
        controller = getattr(qt.QApplication.instance(), '_commonutils_theme', None)
        self.theme_mode.setCurrentIndex(self.theme_mode.findData(controller.mode if controller else 'system'))
        self.theme_mode.currentIndexChanged.connect(self._appearance_changed)
        appearance.addWidget(self.theme_mode)
        appearance.addStretch()
        self.layout().insertLayout(0, appearance)

    def _load_snow(self):
        with qt.QSignalBlocker(self.snow_choice):
            self.snow_choice.setChecked(self._snow_store.safe_values(self.scope).get(self._snow_field, 'true').lower() == 'true')

    def _save_snow(self, enabled):
        try:
            self._snow_store.save({self._snow_field: str(enabled).lower()}, scope=self.scope)
            self.snow_status.setText('')
        except (OSError, ValueError) as error:
            self._load_snow()
            self.snow_status.setText(str(error))

    def set_scope(self, scope):
        super().set_scope(scope)
        self.scope = scope
        if hasattr(self, 'snow_choice'):
            self._load_snow()

    def _appearance_changed(self, index):
        from commonUtils.ui.appearance.theme import apply_theme
        apply_theme(mode=self.theme_mode.itemData(index))
