"""Bounded SRT/WebVTT text cues; embedded tracks belong to the decoder."""
from bisect import bisect_right
from dataclasses import dataclass
import re

MAX_SUBTITLE = 8 * 1024 * 1024
STAMP = r'(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})'
TIMING = re.compile(STAMP + r'\s+-->\s+' + STAMP)


def timestamp(parts):
    hours, minutes, seconds, milliseconds = map(int, parts)
    if minutes > 59 or seconds > 59:
        raise ValueError('Invalid subtitle timestamp.')
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds


@dataclass(frozen=True)
class Cue:
    start: int
    end: int
    text: str


class Subtitles:
    def __init__(self, raw):
        if len(raw) > MAX_SUBTITLE:
            raise ValueError('Subtitles exceed 8 MiB.')
        text = raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
        cues = []
        for block in re.split(r'\n\s*\n', text.strip()):
            lines = block.splitlines()
            for index, line in enumerate(lines[:2]):
                match = TIMING.fullmatch(line.strip())
                if match:
                    start, end = timestamp(match.groups()[:4]), timestamp(match.groups()[4:])
                    if end <= start:
                        raise ValueError('Subtitle ends before it starts.')
                    # Render plain text, never HTML or a subtitle URL.
                    caption = re.sub(r'<[^>]*>', '', '\n'.join(lines[index + 1:]))
                    cues.append(Cue(start, end, caption))
                    break
        if not cues:
            raise ValueError('No valid SRT subtitle cues were found (use UTF-8).')
        if len(cues) > 100000:
            raise ValueError('Too many subtitle cues.')
        self.cues = sorted(cues, key=lambda cue: cue.start)
        self.starts = [cue.start for cue in self.cues]
        self.max_duration = max(cue.end - cue.start for cue in self.cues)

    def at(self, milliseconds):
        start = bisect_right(self.starts, milliseconds - self.max_duration)
        end = bisect_right(self.starts, milliseconds)
        return '\n'.join(cue.text for cue in self.cues[start:end] if cue.start <= milliseconds < cue.end)
