"""Session feature controls with dependency-aware enable/disable behavior."""

from commonUtils.ui import pyside as qt
from features import registry


class FeaturesPage(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        description = qt.QLabel('Enable or disable features for this session. Enabling a feature also enables its '
                                'required dependencies. Existing windows and jobs can finish. Changes reset on restart.')
        description.setWordWrap(True)
        layout.addWidget(description)
        self.tree = qt.QTreeWidget()
        self.tree.setHeaderLabels(['Feature', 'State', 'Requires', 'Required by enabled features'])
        self.tree.setRootIsDecorated(False)
        self.tree.setAccessibleName('Enabled Logistics features')
        self.tree.header().setSectionResizeMode(qt.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tree, 1)
        self.status = qt.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.tree.itemChanged.connect(self._item_changed)
        self._unsubscribe = registry.subscribe(self._features_changed)
        self.destroyed.connect(self._unsubscribe)
        self.refresh()

    def _features_changed(self):
        qt.QTimer.singleShot(0, self.refresh)

    def refresh(self):
        with qt.QSignalBlocker(self.tree):
            self.tree.clear()
            states = sorted(registry.get_feature_states(), key=lambda state: state.label.casefold())
            labels = {state.name: state.label for state in states}
            for state in states:
                text = 'Enabled' if state.enabled else 'Disabled' if state.available else 'Missing dependency'
                item = qt.QTreeWidgetItem([state.label, text,
                    ', '.join(labels.get(name, name) for name in state.dependencies),
                    ', '.join(labels.get(name, name) for name in state.dependents)])
                item.setData(0, qt.Qt.ItemDataRole.UserRole, state.name)
                if state.available:
                    item.setFlags(item.flags() | qt.Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(0, qt.Qt.CheckState.Checked if state.enabled else qt.Qt.CheckState.Unchecked)
                else:
                    item.setFlags(item.flags() & ~qt.Qt.ItemFlag.ItemIsUserCheckable)
                    item.setToolTip(0, 'Required feature packages are missing.')
                self.tree.addTopLevelItem(item)

    def _item_changed(self, item, column):
        if column != 0:
            return
        name = item.data(0, qt.Qt.ItemDataRole.UserRole)
        enabled = item.checkState(0) == qt.Qt.CheckState.Checked
        try:
            registry.set_feature_enabled(name, enabled)
        except Exception as error:
            self.status.setText(str(error))
            self.refresh()
        else:
            self.status.setText(f'{item.text(0)} {"enabled" if enabled else "disabled"} for this session.')
