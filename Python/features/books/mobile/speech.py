"""Compatibility entry for reusable speech sessions and UTF-16 utterances."""
from time import monotonic
from commonUtils.runtime.speech import PlaybackTimer, utterances, SpeechSession as _SpeechSession


class SpeechSession(_SpeechSession):
    def __init__(self, engine, *, on_range, on_state):
        super().__init__(engine, on_range=on_range, on_state=on_state, clock=lambda: monotonic())
