"""Qt decoder boundary; retained providers and authorization belong to the host."""

from dataclasses import dataclass

from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget

from .audio_output import audio_output


@dataclass(frozen=True)
class PlaybackCapabilities:
    external_formats: tuple[str, ...] = (".srt", ".vtt")
    embedded_subtitle_adjustment: bool = False
    audio_delay: bool = False
    receivers: bool = False


class QtPlayback:
    capabilities = PlaybackCapabilities()

    def __init__(self, owner):
        self.player = QMediaPlayer(owner)
        self.audio = audio_output(owner)
        self.audio.setVolume(.8)
        self.player.setAudioOutput(self.audio)
        self.video = QVideoWidget()
        self.player.setVideoOutput(self.video)

    def retire(self):
        from PySide6.QtCore import QUrl

        self.audio.setMuted(True)
        self.player.stop()
        self.player.setSource(QUrl())
