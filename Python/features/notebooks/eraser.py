"""Cut native polylines with a swept circular eraser in page coordinates."""
from dataclasses import replace
import math
from uuid import uuid4

SIZES = {'Small': 8, 'Medium': 16, 'Large': 32}
_INDEX_THRESHOLD = 16


def _sweeps(path):
    """Discard repeated/collinear samples without changing the swept region."""
    corners = []
    for point in path:
        if corners and point[:2] == corners[-1][:2]:
            continue
        while len(corners) >= 2:
            a, b = corners[-2:]
            dx, dy = b[0] - a[0], b[1] - a[1]
            ex, ey = point[0] - b[0], point[1] - b[1]
            if dx * ey != dy * ex or dx * ex + dy * ey < 0:
                break
            corners.pop()
        corners.append(point)
    return list(zip(corners, corners[1:])) or [(path[0], path[0])]


def _intervals(a, b, c, d, radius):
    """Parameter intervals of AB inside the capsule CD (including sparse input)."""
    vx, vy = b[0] - a[0], b[1] - a[1]
    dx, dy = d[0] - c[0], d[1] - c[1]
    length = dx * dx + dy * dy
    projection = ((a[0] - c[0]) * dx + (a[1] - c[1]) * dy) / length if length else 0
    slope = (vx * dx + vy * dy) / length if length else 0
    cuts = sorted({0., 1., *(t for t in ((-projection / slope, (1 - projection) / slope) if slope else ()) if 0 < t < 1)})
    r0, dr = radius + a[3] / 2, (b[3] - a[3]) / 2
    result = []
    for lo, hi in zip(cuts, cuts[1:]):
        u = projection + slope * (lo + hi) / 2
        if length and 0 < u < 1:
            x, y = a[0] - c[0] - projection * dx, a[1] - c[1] - projection * dy
            sx, sy = vx - slope * dx, vy - slope * dy
        else:
            end = d if u >= 1 else c
            x, y, sx, sy = a[0] - end[0], a[1] - end[1], vx, vy
        aa = sx * sx + sy * sy - dr * dr
        bb = 2 * (x * sx + y * sy - r0 * dr)
        cc = x * x + y * y - r0 * r0
        roots = []
        if abs(aa) < 1e-20:
            if abs(bb) > 1e-20:
                roots.append(-cc / bb)
        else:
            disc = bb * bb - 4 * aa * cc
            if disc >= 0:
                root = math.sqrt(disc)
                roots.extend(((-bb - root) / (2 * aa), (-bb + root) / (2 * aa)))
        boundaries = sorted({lo, hi, *(t for t in roots if lo < t < hi)})
        for left, right in zip(boundaries, boundaries[1:]):
            mid = (left + right) / 2
            if aa * mid * mid + bb * mid + cc <= 0:
                result.append((left, right))
    return result


def erase(strokes, layers, path, radius, whole=False):
    visible = {key for key, _, shown in layers if shown}
    sweeps = _sweeps(path)
    # Index the eraser path, rather than comparing every digitizer sample with
    # every ink segment. Keep long sweeps separate to bound index storage.
    cell = 32
    grid, wide = {}, []
    for index, (c, d) in enumerate(sweeps if len(sweeps) > _INDEX_THRESHOLD else ()):
        left, right = math.floor((min(c[0], d[0]) - radius) / cell), math.floor((max(c[0], d[0]) + radius) / cell)
        top, bottom = math.floor((min(c[1], d[1]) - radius) / cell), math.floor((max(c[1], d[1]) + radius) / cell)
        if (right - left + 1) * (bottom - top + 1) > 16:
            wide.append(index)
            continue
        for x in range(left, right + 1):
            for y in range(top, bottom + 1):
                grid.setdefault((x, y), []).append(index)
    result = []
    candidate_cache = {}
    cached_candidates = 0
    for stroke in strokes:
        if stroke.layer not in visible or not stroke.points:
            result.append(stroke)
            continue
        pieces, current, touched = [], [], False
        pairs = list(zip(stroke.points, stroke.points[1:])) or [(stroke.points[0], stroke.points[0])]
        for a, b in pairs:
            reach = radius + max(a[3], b[3]) / 2
            intervals = []
            half = max(a[3], b[3]) / 2
            candidates = None
            if len(sweeps) > _INDEX_THRESHOLD:
                key = (math.floor((min(a[0], b[0]) - half) / cell), math.floor((max(a[0], b[0]) + half) / cell),
                       math.floor((min(a[1], b[1]) - half) / cell), math.floor((max(a[1], b[1]) + half) / cell))
                candidates = candidate_cache.get(key)
                if candidates is None:
                    found = set(wide)
                    for x in range(key[0], key[1] + 1):
                        for y in range(key[2], key[3] + 1):
                            found.update(grid.get((x, y), ()))
                    candidates = sorted(found)
                    # Imported variable-width segments can have many distinct
                    # bounds. Keep this per-contact acceleration bounded too.
                    if len(candidate_cache) < 2048 and cached_candidates + len(candidates) <= 65536:
                        candidate_cache[key] = candidates
                        cached_candidates += len(candidates)
            for index in candidates if candidates is not None else range(len(sweeps)):
                c, d = sweeps[index]
                if (max(a[0], b[0]) + reach < min(c[0], d[0]) or min(a[0], b[0]) - reach > max(c[0], d[0])
                        or max(a[1], b[1]) + reach < min(c[1], d[1]) or min(a[1], b[1]) - reach > max(c[1], d[1])):
                    continue
                cuts = _intervals(a, b, c, d, radius)
                intervals.extend(cuts)
                if (whole and cuts) or any(lo == 0 and hi == 1 for lo, hi in cuts):
                    break
            if whole and intervals:
                touched = True
                break
            cursor = 0.
            def point(t):
                # Uncut endpoints are immutable ink values. Reusing them avoids
                # allocating two coordinate lists per untouched segment.
                if t == 0:
                    return a
                if t == 1:
                    return b
                return [x + (y - x) * t for x, y in zip(a, b)]
            for lo, hi in sorted(intervals):
                if hi <= cursor:
                    continue
                touched = True
                if lo > cursor:
                    if not current:
                        current = [point(cursor)]
                    current.append(point(lo))
                if current:
                    pieces.append(current)
                    current = []
                cursor = max(cursor, hi)
            if cursor < 1:
                if not current:
                    current = [point(cursor)]
                current.append(point(1))
        if current:
            pieces.append(current)
        if not touched:
            result.append(stroke)
        elif not whole:
            for index, points in enumerate(pieces):
                result.append(replace(stroke, id=stroke.id if index == 0 else uuid4().hex, points=points))
    if sum(len(s.points) for s in result) > 1_000_000 or any(len(s.points) > 100_000 for s in result):
        raise ValueError('Erasing would exceed the page ink limit.')
    return result
