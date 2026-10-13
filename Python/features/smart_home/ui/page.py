"""
Smart Home page for the Logistics feature UI.
"""

from commonUtils.ui.appearance.typography import point_size, setting_size
from commonUtils.ui import pyside
from commonUtils.ui.tasks.operation_progress import OperationProgress

from features.smart_home.philips_hue import api as philips_hue


ROOMS = (
    'Living Room',
    'Bedroom',
    'Kitchen',
)

BRIGHTNESS_ACTIONS = (
    ('OFF', {'State': False}),
    ('1%', {'State': True, 'Brightness': 0}),
    ('50%', {'State': True, 'Brightness': 127}),
    ('100%', {'State': True, 'Brightness': 254}),
    ('ON', {'State': True}),
)

COLOR_ACTIONS = (
    ('Red', 'Red'),
    ('Orange', 'Orange'),
    ('Yellow', 'Yellow'),
    ('Green', 'Green'),
    ('Aqua', 'Aqua'),
    ('Blue', 'Blue'),
    ('Purple', 'Purple'),
    ('Magenta', 'Magenta'),
    ('White', 'White'),
)


class SmartHomePage(pyside.QWidget):
    idle = pyside.Signal()
    def __init__(self, parent=None):
        super().__init__(parent)

        self.scroll = pyside.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(pyside.QFrame.Shape.NoFrame)

        self.task = OperationProgress(self)
        self.task.completed.connect(self._finished)
        self.task.completed.connect(lambda *args: self.idle.emit())
        self._build_layout()
        self._populate_rooms()

    def _build_layout(self):
        root_layout = pyside.QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        header_layout = pyside.QHBoxLayout()

        title_container = pyside.QWidget()
        title_layout = pyside.QVBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(4)

        title = pyside.QLabel('Smart Home')
        title_font = title.font()
        title_font.setPointSizeF(point_size(setting_size(title_font) + 7))
        title_font.setBold(True)
        title.setFont(title_font)

        description = pyside.QLabel(
            'Philips Hue room controls.'
        )
        description.setWordWrap(True)

        title_layout.addWidget(title)
        title_layout.addWidget(description)

        connect_button = pyside.QPushButton('Connect Bridge')
        connect_button.setToolTip('Connect/register with the configured Philips Hue bridge.')
        connect_button.clicked.connect(lambda: self._run(philips_hue.connect_bridge))
        self.connect_button = connect_button
        refresh_button = pyside.QPushButton('Find rooms')
        refresh_button.clicked.connect(lambda: self._run(philips_hue.get_rooms))

        header_layout.addWidget(title_container, 1)
        header_layout.addWidget(connect_button)
        header_layout.addWidget(refresh_button)
        self.refresh_button = refresh_button

        root_layout.addLayout(header_layout)
        root_layout.addWidget(self.scroll, 1)
        root_layout.addWidget(self.task)

    def _populate_rooms(self, rooms=ROOMS):
        content = pyside.QWidget()
        layout = pyside.QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        for room_name in rooms:
            layout.addWidget(self._create_room_group(room_name))

        layout.addStretch()
        self.scroll.setWidget(content)

    def _create_room_group(self, room_name: str):
        group = pyside.QGroupBox(room_name)
        layout = pyside.QVBoxLayout(group)
        layout.setSpacing(10)

        brightness_label = pyside.QLabel('Power / Brightness')
        brightness_font = brightness_label.font()
        brightness_font.setBold(True)
        brightness_label.setFont(brightness_font)

        brightness_layout = pyside.QHBoxLayout()
        brightness_layout.setSpacing(8)

        for label, values in BRIGHTNESS_ACTIONS:
            button = pyside.QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, room_name=room_name, values=values:
                    self._set_room(room_name, values)
            )
            brightness_layout.addWidget(button)

        color_label = pyside.QLabel('Color')
        color_font = color_label.font()
        color_font.setBold(True)
        color_label.setFont(color_font)

        color_layout = pyside.QGridLayout()
        color_layout.setHorizontalSpacing(8)
        color_layout.setVerticalSpacing(8)

        for index, (label, color_name) in enumerate(COLOR_ACTIONS):
            button = pyside.QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, room_name=room_name, color_name=color_name:
                    self._set_room(
                        room_name,
                        {
                            'State': True,
                            'Color': color_name,
                        }
                    )
            )

            row = index // 5
            column = index % 5
            color_layout.addWidget(button, row, column)

        for column in range(5):
            color_layout.setColumnStretch(column, 1)

        layout.addWidget(brightness_label)
        layout.addLayout(brightness_layout)
        layout.addWidget(color_label)
        layout.addLayout(color_layout)

        return group

    def _set_room(self, room_name: str, values: dict):
        arguments = {
            'Room': room_name,
            **values,
        }

        self._run(lambda: philips_hue.set_group_prop_from_arg_dict(arguments))

    def _run(self, callback):
        if self.task.busy:
            return
        self.scroll.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.task.start(lambda report, cancelled: None if cancelled() else callback(),
                        message='Contacting Hue bridge…')

    def _finished(self, result, error):
        self.scroll.setEnabled(True)
        self.connect_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        if not error and isinstance(result, tuple):
            self._populate_rooms(result)
            if not result:
                self.task.message.setText('No rooms found on this bridge.')

    def prepare_close(self):
        if self.task.busy:
            self.task.request_cancel()
            return False
        return True

    def closeEvent(self, event):
        if not self.prepare_close():
            event.ignore()
        else:
            super().closeEvent(event)
