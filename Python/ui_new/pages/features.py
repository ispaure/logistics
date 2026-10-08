"""Session feature controls with dependency-aware enable/disable behavior."""

from pathlib import Path

from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import open_markdown
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
        self.tree.setHeaderLabels(['Feature', 'State', 'Requires', 'Required by enabled features', 'Help'])
        self.tree.setRootIsDecorated(False)
        self.tree.setAccessibleName('Enabled Logistics features')
        self.tree.header().setSectionResizeMode(qt.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(3, qt.QHeaderView.ResizeMode.Stretch)
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
                guide = Path(registry.__file__).parent / state.name / 'user_docs' / 'index.md'
                help_button = qt.QPushButton('User guide')
                help_button.setAccessibleName(f'{state.label} user guide')
                help_button.setEnabled(guide.is_file())
                help_button.setToolTip('Open user documentation (hold Alt to edit)' if guide.is_file() else 'No user guide is installed.')
                help_button.clicked.connect(lambda checked=False, path=guide: open_markdown(path, parent=self.window()))
                self.tree.setItemWidget(item, 4, help_button)

    def _item_changed(self, item, column):
        if column != 0:
            return
        name = item.data(0, qt.Qt.ItemDataRole.UserRole)
        enabled = item.checkState(0) == qt.Qt.CheckState.Checked
        try:
            registry.set_feature_enabled(name, enabled)
        except Exception as error:
            self.status.setText(str(error))
            # The signal came from this item: clearing it before setCheckState
            # unwinds can crash native Qt. Rebuild after signal delivery ends.
            self._features_changed()
        else:
            self.status.setText(f'{item.text(0)} {"enabled" if enabled else "disabled"} for this session.')
