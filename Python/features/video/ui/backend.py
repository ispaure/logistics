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


def desktop_playback(owner):
    """Prefer verified native colour output on Cocoa; retain VLC elsewhere."""
    from services.documents.video_settings import SettingsStore
    settings = owner.progress.settings
    if settings is None:
        from commonUtils.filesystem.storage import cache_directory
        settings = SettingsStore(cache_directory(create=False) / 'Video').load()
    if settings.renderer != 'compatibility':
        from commonUtils.ui import pyside as qt
        if qt.QApplication.platformName() == 'cocoa':
            from .mpv_backend import MPVPlayback
            try:
                return MPVPlayback(owner)
            except (OSError, RuntimeError, ValueError):
                owner._renderer_warning = 'Colour output is unavailable. Using compatibility playback; Picture → Renderer can retry.'
    from .vlc_backend import VLCPlayback
    return VLCPlayback(owner)
