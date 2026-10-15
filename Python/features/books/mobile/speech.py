"""Bounded utterances, UTF-16 ranges and session-owned native read-aloud."""
from bisect import bisect_left
from features.books.locations import utf16_length


def utterances(text, start=0, end=None, *, limit=1000, breaks=()):
    """Keep browser offsets intact, including astral characters and block edges."""
    units = [0]
    for char in text:
        units.append(units[-1] + utf16_length(char))
    left = bisect_left(units, max(0, start))
    right = bisect_left(units, units[-1] if end is None else min(units[-1], max(start, end)))
    boundaries = set(breaks)
    while left < right:
        while left < right and text[left].isspace():
            left += 1
        if left >= right:
            break
        stop = left + 1
        while stop < right and units[stop + 1] - units[left] <= limit:
            if units[stop] in boundaries or (text[stop - 1] in '.!?。！？' and text[stop].isspace()):
                break
            stop += 1
        if stop < right and units[stop] not in boundaries and text[stop - 1] not in '.!?。！？' and not text[stop - 1].isspace():
            space = text.rfind(' ', left + 1, stop)
            if space >= left + (stop - left) // 2:
                stop = space + 1
        yield text[left:stop], units[left], units[stop]
        left = stop


class SpeechSession:
    def __init__(self, engine, *, on_range, on_state):
        self.engine, self.on_range, self.on_state = engine, on_range, on_state
        self.closed, self.state, self.generation = False, 'stopped', 0
        self.ranges, self.index = [], 0
        engine.completed = self.completed
        engine.failed = self.failed

    def play(self, text, start=0, end=None, *, voice='', speed=1, breaks=()):
        if self.closed:
            return
        self.stop()
        if not self.engine.ready:
            self.on_state('unavailable', self.engine.error or 'Speech engine is starting.')
            return
        self.ranges = list(utterances(text, start, end, breaks=breaks))
        self.voice, self.speed, self.index = voice, speed, 0
        if self.ranges:
            self.state = 'speaking'
            self.next()
        else:
            self.on_state('stopped', 'No text to read from this passage.')

    def next(self):
        if self.closed or self.state != 'speaking':
            return
        if self.index >= len(self.ranges):
            self.stop()
            self.on_state('stopped', 'Finished the selected passage or current chapter.')
            return
        text, start, end = self.ranges[self.index]
        self.on_range(start, end)
        self.generation += 1
        self.token = str(self.generation)
        try:
            self.engine.speak(text, self.voice, self.speed, self.token)
            self.on_state('speaking', 'Reading aloud · current sentence highlighted')
        except Exception:
            self.stop()
            self.on_state('unavailable', 'Speech failed. Check the installed offline voice.')

    def completed(self, token):
        if not self.closed and self.state == 'speaking' and token == self.token:
            self.index += 1
            self.next()

    def failed(self, token):
        if not self.closed and token == self.token:
            self.stop()
            self.on_state('unavailable', 'Offline speech failed. Choose another installed voice.')

    def pause(self):
        if self.state == 'speaking':
            self.state = 'paused'
            self.engine.stop()
            self.generation += 1
            self.token = str(self.generation)
            self.on_state('paused', 'Paused · Resume repeats the current sentence.')

    def resume(self):
        if not self.closed and self.state == 'paused':
            self.state = 'speaking'
            self.next()

    def stop(self):
        self.generation += 1
        self.token = str(self.generation)
        self.state = 'stopped'
        self.engine.stop()
        self.ranges, self.index = [], 0
        self.on_state('stopped', 'Stopped')

    def dispose(self):
        if not self.closed:
            self.stop()
            self.closed = True
            self.engine.close()
            self.engine.completed = self.engine.failed = lambda *args: None
            self.on_range = self.on_state = lambda *args: None
