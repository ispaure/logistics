"""Qt decoder boundary; retained providers and authorization belong to the host."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from dataclasses import dataclass

from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget

from .audio_output import audio_output


AUDIO_SWITCH_TIMEOUT = 8
AUDIO_SWITCH_ERROR = 'Could not switch audio. Choose another track or press Play to retry.'
VIDEO_WITHOUT_AUDIO = 'Audio has not started here. Video continues.'
SEEK_TIMEOUT = 8
OPEN_TIMEOUT = 20
UNKNOWN_DURATION = 'Duration unknown'
OPEN_ERROR = 'Could not open this video. Its container or codecs may be unsupported, or the file may be damaged.'
AUDIO_VIDEO_ERROR = 'No playable audio or video was found. Try a supported codec or another copy.'
VIDEO_TRACK_ERROR = 'The video track could not be decoded. Try another copy or a supported video codec.'
SEEK_ERROR = 'Could not seek to this position. Use Playback → Start over or Go to time.'
AUDIO_ONLY_MESSAGE = 'Continuing audio. Seek back to restore video.'


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
