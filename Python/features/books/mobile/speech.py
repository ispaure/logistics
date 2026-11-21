"""Compatibility entry for reusable speech sessions and UTF-16 utterances."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from time import monotonic
from commonUtils.runtime.speech import PlaybackTimer, utterances, SpeechSession as _SpeechSession


class SpeechSession(_SpeechSession):
    def __init__(self, engine, *, on_range, on_state):
        super().__init__(engine, on_range=on_range, on_state=on_state, clock=lambda: monotonic())
