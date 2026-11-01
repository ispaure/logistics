"""Video buffering policy and shared, revocable memory ranges.

Tune DEFAULT_BUFFERING here. The 128 MiB rewind cache holds about one minute
at 18 Mbit/s; higher bitrates need a larger budget. No plaintext is staged.
"""
from collections import OrderedDict
from dataclasses import dataclass
from threading import Condition


@dataclass(frozen=True)
class BufferingPolicy:
    memory_bytes: int = 128 * 1024 * 1024
    range_bytes: int = 1024 * 1024  # Bound first-read/seek latency; native maximum is 4 MiB.
    read_ahead_chunks: int = 12
    chunk_bytes: int = 1024 * 1024
    stall_seconds: float = .5

    def __post_init__(self):
        if (not 0 < self.range_bytes <= 4 * 1024 * 1024
                or self.memory_bytes < self.range_bytes or self.read_ahead_chunks < 1
                or not 0 < self.chunk_bytes <= self.range_bytes or self.stall_seconds < 0):
            raise ValueError('Invalid video buffering policy.')


DEFAULT_BUFFERING = BufferingPolicy()


class MemoryRanges:
    """One bounded LRU across HTTP streams, coalescing concurrent block reads."""
    def __init__(self, size, policy, check):
        self.size, self.policy, self.check = size, policy, check
        self.condition = Condition()
        self.blocks = OrderedDict()
        self.inflight = set()
        self.bytes = 0
        self.closed = False

    def read(self, offset, count, stream):
        if offset % self.policy.range_bytes or count != min(self.policy.range_bytes, self.size - offset):
            raise ValueError('Invalid video memory range.')
        self.check()
        with self.condition:
            while True:
                if self.closed:
                    raise PermissionError('Video memory cache is closed.')
                self.check()
                if offset in self.blocks:
                    self.blocks.move_to_end(offset)
                    return self.blocks[offset]
                if offset not in self.inflight:
                    self.inflight.add(offset)
                    break
                self.condition.wait(.05)
        try:
            stream.seek(offset)
            data = stream.read(count)
            self.check()
            if not isinstance(data, bytes) or len(data) != count:
                raise OSError('Incomplete video memory range.')
            with self.condition:
                if self.closed:
                    raise PermissionError('Video memory cache is closed.')
                self.blocks[offset] = data
                self.bytes += len(data)
                while self.bytes > self.policy.memory_bytes:
                    _, retired = self.blocks.popitem(last=False)
                    self.bytes -= len(retired)
            return data
        finally:
            with self.condition:
                self.inflight.discard(offset)
                self.condition.notify_all()

    def ranges(self):
        self.check()
        with self.condition:
            merged = []
            for offset, data in sorted(self.blocks.items()):
                stop = offset + len(data)
                if merged and offset <= merged[-1][1]: merged[-1][1] = max(stop,merged[-1][1])
                else: merged.append([offset,stop])
            return [[start/self.size,stop/self.size] for start,stop in merged]

    def close(self):
        with self.condition:
            self.closed = True
            self.blocks.clear()
            self.bytes = 0
            self.condition.notify_all()


def map_cached_ranges_to_time(ranges, anchors):
    """Map byte-normalized cached intervals using trustworthy (byte,time) index anchors.

    Both coordinates are normalized to [0,1].  Sparse indexes are useful for
    display only: this does not assert that a segment is continuously decodable.
    Return None for missing/invalid metadata so callers retain the byte fallback.
    """
    from bisect import bisect_right
    import math
    if not isinstance(anchors, (list, tuple)) or len(anchors) < 2:
        return None
    try:
        points = [(float(byte), float(timestamp)) for byte, timestamp in anchors]
        if any(not math.isfinite(x) or not math.isfinite(t) or x < 0 or t < 0 or x > 1 or t > 1
               for x, t in points):
            return None
        if any(points[i][0] >= points[i+1][0] or points[i][1] > points[i+1][1]
               for i in range(len(points)-1)):
            return None
        if points[0] != (0.0, 0.0) or points[-1] != (1.0, 1.0):
            return None
        def project(x):
            x = max(0., min(1., float(x)))
            i = max(0, min(len(points)-2, bisect_right(points, (x, 1.)) - 1))
            a, ta = points[i]; b, tb = points[i+1]
            return ta + (tb-ta) * (x-a)/(b-a)
        result = []
        for a, b in ranges:
            a, b = float(a), float(b)
            if not (math.isfinite(a) and math.isfinite(b) and 0 <= a <= b <= 1):
                return None
            result.append([project(a), project(b)])
        return result
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        return None
