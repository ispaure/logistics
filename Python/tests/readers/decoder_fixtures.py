"""Native desktop decoder fixtures for hosts with and without Qt Multimedia."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

def headless_vlc_playback(owner):
    """Exercise the production decoder without requiring a host speaker device."""
    from features.video.ui.vlc_backend import VLCPlayback
    backend = VLCPlayback(owner, interactive=False)
    backend.player.native.audio_output_set('adummy')
    return backend


def require_qt_decoder(case):
    """Qt is optional compatibility coverage; production VLC remains required."""
    from PySide6.QtMultimedia import QMediaFormat
    if not QMediaFormat().supportedFileFormats(QMediaFormat.ConversionMode.Decode):
        case.skipTest('This host has no optional Qt Multimedia decoder; production VLC is tested separately')
