"""
Links page for the replacement Logistics UI.
"""

from commonUtils.ui import pyside

from features.links import actions, catalog


class LinksPage(pyside.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.scroll = pyside.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(pyside.QFrame.Shape.NoFrame)

        self._build_layout()
        self._populate_links()

    def _build_layout(self):
        root_layout = pyside.QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        title = pyside.QLabel('Links')
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 7)
        title_font.setBold(True)
        title.setFont(title_font)

        description = pyside.QLabel(
            'Frequently used web links grouped by purpose.'
        )
        description.setWordWrap(True)

        root_layout.addWidget(title)
        root_layout.addWidget(description)
        root_layout.addWidget(self.scroll, 1)

    def _populate_links(self):
        content = pyside.QWidget()
        layout = pyside.QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        for category in catalog.LINK_CATEGORIES:
            layout.addWidget(self._create_category(category))

        layout.addStretch()
        self.scroll.setWidget(content)

    def _create_category(self, category: catalog.LinkCategory):
        group_box = pyside.QGroupBox(category.name)
        group_layout = pyside.QVBoxLayout(group_box)
        group_layout.setSpacing(12)

        for link_group in category.groups:
            if link_group.name:
                group_label = pyside.QLabel(link_group.name)
                group_font = group_label.font()
                group_font.setBold(True)
                group_label.setFont(group_font)
                group_layout.addWidget(group_label)

            buttons_layout = pyside.QGridLayout()
            buttons_layout.setHorizontalSpacing(8)
            buttons_layout.setVerticalSpacing(8)

            for index, link in enumerate(link_group.links):
                button = pyside.QPushButton(link.label)
                button.clicked.connect(
                    lambda _checked=False, config_key=link.config_key: actions.open_config_file_url(config_key)
                )

                row = index // 4
                column = index % 4
                buttons_layout.addWidget(button, row, column)

            for column in range(4):
                buttons_layout.setColumnStretch(column, 1)

            group_layout.addLayout(buttons_layout)

        return group_box
