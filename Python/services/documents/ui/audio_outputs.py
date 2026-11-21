"""Observe changes to the default output used by desktop playback."""
from commonUtils.ui import pyside as qt
from PySide6.QtMultimedia import QMediaDevices


class SelectedAudioOutput(qt.QObject):
    changed = qt.Signal(bool)  # Whether a previous default was identifiable.

    def __init__(self, parent):
        super().__init__(parent)
        self.devices = QMediaDevices(self)
        self.selected = bytes(self.devices.defaultAudioOutput().id())
        self.devices.audioOutputsChanged.connect(self.refresh)

    def refresh(self):
        previous = self.selected
        current = bytes(self.devices.defaultAudioOutput().id())
        self.selected = current
        if current != previous or (previous and previous not in
                {bytes(device.id()) for device in self.devices.audioOutputs()}):
            self.changed.emit(bool(previous))
