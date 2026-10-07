"""
Feature-contributed maintenance actions.
"""

from commonUtils.ui import pyside

from features import registry
from features.contributions import DebugActionContribution
from ui_new.actions import execute_action


class DebugPage(pyside.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.scroll = pyside.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(pyside.QFrame.Shape.NoFrame)

        self._build_layout()
        self.refresh()

    def _build_layout(self):
        root_layout = pyside.QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        title = pyside.QLabel('Debug')
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 7)
        title_font.setBold(True)
        title.setFont(title_font)

        description = pyside.QLabel(
            'Feature-provided maintenance, conversion, diagnostic, and development tools.'
        )
        description.setWordWrap(True)

        root_layout.addWidget(title)
        root_layout.addWidget(description)
        self.open_browser_button = pyside.QPushButton('Open File Browser…')
        self.open_browser_button.setToolTip('Choose a folder and browse with available Logistics features.')
        self.open_browser_button.clicked.connect(self._open_file_browser)
        root_layout.addWidget(self.open_browser_button)
        root_layout.addWidget(self.scroll, 1)

    def _open_file_browser(self):
        from ui_new.file_browser import open_file_browser
        return open_file_browser(self.window())

    def refresh(self):
        """Rebuild the page from all enabled feature Debug contributions."""

        content = pyside.QWidget()
        layout = pyside.QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        registered_actions = registry.get_debug_actions()

        if not registered_actions:
            empty = pyside.QLabel('No enabled features currently contribute Debug actions.')
            empty.setWordWrap(True)
            layout.addWidget(empty)
            layout.addStretch()
            self.scroll.setWidget(content)
            return

        actions_by_feature = {}

        for registered in registered_actions:
            actions_by_feature.setdefault(
                (registered.feature_label, registered.feature_name),
                []
            ).append(registered.contribution)

        for (feature_label, _feature_name), actions in sorted(
            actions_by_feature.items(),
            key=lambda item: item[0][0].casefold()
        ):
            layout.addWidget(self._create_feature_group(feature_label, actions))

        layout.addStretch()
        self.scroll.setWidget(content)

    def _create_feature_group(self, feature_label: str, actions: list[DebugActionContribution]):
        group = pyside.QGroupBox(feature_label)
        grid = pyside.QGridLayout(group)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        sorted_actions = sorted(
            actions,
            key=lambda action: (action.order, action.name.casefold())
        )

        for index, action in enumerate(sorted_actions):
            button = pyside.QPushButton(action.name)
            button.setEnabled(action.enabled)

            if action.description is not None:
                button.setToolTip(action.description)

            button.clicked.connect(
                lambda _checked=False, action=action: self._execute_action(action)
            )

            row = index // 2
            column = index % 2
            grid.addWidget(button, row, column)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        return group

    def _execute_action(self, action: DebugActionContribution):
        return execute_action(action, self)
