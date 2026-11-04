"""Conservative reduction of newly computed native stroke samples.

This does not smooth, resample or decode imported ink. Call it only after the
new stroke's calibrated widths have been computed, never on native scene rows.
Every retained row is an original sample. Error bounds use the original path's
cumulative arc length, including both raw and codec-rounded pressure.
"""
import math
import struct

POSITION_TOLERANCE = .125
PRESSURE_TOLERANCE = 1 / 255
WIDTH_TOLERANCE = .0625
NATIVE_X_ORIGIN = 702.
_NATIVE_XY = struct.Struct('<ff')


def _extrema(values, mandatory):
    """Keep both edges of a plateau which is a local maximum or minimum."""
    start = 0
    while start < len(values):
        end = start
        while end + 1 < len(values) and values[end + 1] == values[start]:
            end += 1
        if start and end + 1 < len(values):
            before, after = values[start] - values[start - 1], values[end + 1] - values[end]
            if before * after < 0:
                mandatory[start] = mandatory[end] = 1
        start = end + 1


def _anchors(points, pressure_codes, native_x_origin):
    mandatory = bytearray(len(points))
    mandatory[0] = mandatory[-1] = 1
    _extrema(pressure_codes, mandatory)
    width_codes = [round(point[3] * 4) for point in points]
    _extrema(width_codes, mandatory)
    previous_packet = None
    for i, point in enumerate(points):
        native_x = point[0] - native_x_origin
        if not math.isfinite(native_x):
            return None
        try:
            packet = _NATIVE_XY.pack(native_x, point[1])
        except (OverflowError, struct.error):
            return None
        if i:
            # The actual v6 encoder stores float32(x - native origin, y).
            # Subpixel motion can therefore be a stationary native sample.
            if (packet == previous_packet and
                    (pressure_codes[i] != pressure_codes[i - 1] or width_codes[i] != width_codes[i - 1])):
                mandatory[i - 1] = mandatory[i] = 1
        previous_packet = packet
    for i in range(1, len(points)):
        a, b = points[i - 1], points[i]
        if a[0] == b[0] and a[1] == b[1] and (a[2] != b[2] or a[3] != b[3]):
            # Stationary pressure/width changes are native dynamics, not noise.
            mandatory[i - 1] = mandatory[i] = 1
        if i + 1 == len(points):
            continue
        c = points[i + 1]
        ax, ay, bx, by = b[0] - a[0], b[1] - a[1], c[0] - b[0], c[1] - b[1]
        aa, bb = ax * ax + ay * ay, bx * bx + by * by
        if aa and bb:
            dot, cross = ax * bx + ay * by, ax * by - ay * bx
            if dot <= 0 or cross * cross >= .25 * aa * bb:
                mandatory[i] = 1  # A turn of at least 30 degrees or a reversal.
    return mandatory


def _channels(point, pressure_code):
    return point[0], point[1], point[2], pressure_code / 255, point[3]


def _projected_fields_fit(values, start, span, slopes, minimum, maximum, position_tolerance, field_tolerances):
    if values[0] == start[0] and values[1] == start[1]:
        return False  # A nonempty arc must not collapse onto a zero-length chord.
    if values[2] == start[2] and values[3] == start[3] and values[4] == start[4]:
        return True  # Constant fields have no projection-phase error.
    # A sample's XY residual is its slope difference times its distance from the
    # anchor. Use the span's largest distance to bound every earlier sample,
    # without rescanning them. The position corridor gives a second upper bound.
    dx = max(abs(minimum[0] - slopes[0]), abs(maximum[0] - slopes[0]))
    dy = max(abs(minimum[1] - slopes[1]), abs(maximum[1] - slopes[1]))
    certificate = min(position_tolerance, span * math.hypot(dx, dy))
    if not certificate:
        return True
    chord = math.hypot(values[0] - start[0], values[1] - start[1])
    # Nearest-chord projection can shift the original arc-length fraction by
    # at most certificate/chord. Bound each field's actual arc residual from
    # its slope extrema, then add that possible projection-phase error.
    for channel, tolerance in enumerate(field_tolerances, 2):
        field_slope_error = max(abs(minimum[channel] - slopes[channel]), abs(maximum[channel] - slopes[channel]))
        field_error = min(tolerance, span * field_slope_error)
        phase_error = abs(values[channel] - start[channel]) * certificate / chord
        if field_error + phase_error > tolerance:
            return False
    return True


def retained_indices(points, tool, *, native_x_origin=NATIVE_X_ORIGIN, position_tolerance=POSITION_TOLERANCE,
                     pressure_tolerance=PRESSURE_TOLERANCE, width_tolerance=WIDTH_TOLERANCE):
    """Return ordered original indices with deterministic linear work/storage.

    For every omitted sample, interpolation between its retained neighbors at
    its original arc-length fraction differs by at most ``position_tolerance``
    in Euclidean position, ``pressure_tolerance`` in raw and byte-rounded
    pressure, and ``width_tolerance`` in the already computed diameter.
    The same pressure/width bounds also hold at the original sample's nearest
    projected position on the retained chord, rather than only at arc fraction.
    ``native_x_origin`` matches the v6 scene encoder's horizontal translation;
    its default is half the 1404-unit native page. The owning adapter should
    pass its own WIDTH / 2 rather than duplicating that format constant.

    Byte-pressure/quarter-width extrema, corners, stationary dynamics and
    endpoints remain exact. A heading cone prevents smooth sub-tolerance loops from collapsing
    into a dot. Calligraphy is deliberately exempt: its rendered nib geometry
    also depends on neighboring directions, beyond these scalar bounds.
    """
    for tolerance in (position_tolerance, pressure_tolerance, width_tolerance):
        if type(tolerance) not in (int, float) or not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError('Stroke sampling tolerances must be finite and non-negative.')
    if type(native_x_origin) not in (int, float) or not math.isfinite(native_x_origin):
        raise ValueError('The native scene origin must be finite.')
    for point in points:
        if (len(point) != 4 or any(type(value) not in (int, float) or not math.isfinite(value) for value in point)
                or not 0 <= point[2] <= 1 or point[3] < 0):
            raise ValueError('Expected finite computed stroke points [x, y, pressure, width].')
    if len(points) < 3 or tool == 21:
        return list(range(len(points)))

    pressure_codes = bytearray(round(point[2] * 255) for point in points)
    mandatory = _anchors(points, pressure_codes, native_x_origin)
    if mandatory is None:
        return list(range(len(points)))
    axis_tolerance = position_tolerance / math.sqrt(2)
    field_tolerances = (pressure_tolerance, pressure_tolerance, width_tolerance)
    tolerances = (axis_tolerance, axis_tolerance, *field_tolerances)
    kept = [0]
    anchor, anchor_distance, distance = 0, 0., 0.
    anchor_values = _channels(points[0], pressure_codes[0])
    lower, upper = [-math.inf] * 5, [math.inf] * 5
    heading = minimum = maximum = None

    for i in range(1, len(points)):
        previous_distance = distance
        previous, point = points[i - 1], points[i]
        dx, dy = point[0] - previous[0], point[1] - previous[1]
        step = math.hypot(dx, dy)
        distance += step
        if not math.isfinite(distance) or (step > 0 and distance <= previous_distance):
            # A non-advancing parameter cannot safely interpolate dynamics.
            return list(range(len(points)))
        values = _channels(point, pressure_codes[i])
        span = distance - anchor_distance
        turn = False
        if heading is not None and (dx or dy):
            hx, hy = heading
            dot = hx * dx + hy * dy
            turn = dot <= 0 or 2 * dot * dot < (hx * hx + hy * hy) * (dx * dx + dy * dy)
        slopes = [(value - start) / span for value, start in zip(values, anchor_values)] if span else None
        outside = slopes is not None and any(value < low or value > high
                                             for value, low, high in zip(slopes, lower, upper))
        if not (turn or outside) and slopes is not None and minimum is not None:
            outside = not _projected_fields_fit(values, anchor_values, span, slopes, minimum, maximum,
                                                position_tolerance, field_tolerances)
        if (turn or outside) and i - 1 > anchor:
            # The previous endpoint passed every earlier sample's corridor.
            # Its interpolation is therefore valid for the whole closed span.
            anchor = i - 1
            kept.append(anchor)
            anchor_distance = previous_distance
            anchor_values = _channels(previous, pressure_codes[anchor])
            lower, upper = [-math.inf] * 5, [math.inf] * 5
            heading = minimum = maximum = None
            span = distance - anchor_distance
            slopes = [(value - start) / span for value, start in zip(values, anchor_values)] if span else None
        if slopes is not None:
            for channel, (slope, tolerance) in enumerate(zip(slopes, tolerances)):
                allowance = tolerance / span
                lower[channel] = max(lower[channel], slope - allowance)
                upper[channel] = min(upper[channel], slope + allowance)
            if heading is None and (dx or dy):
                heading = dx, dy
            if minimum is None:
                minimum, maximum = list(slopes), list(slopes)
            else:
                for channel in range(5):
                    minimum[channel] = min(minimum[channel], slopes[channel])
                    maximum[channel] = max(maximum[channel], slopes[channel])
        if mandatory[i]:
            if kept[-1] != i:
                kept.append(i)
            anchor, anchor_distance, anchor_values = i, distance, values
            lower, upper = [-math.inf] * 5, [math.inf] * 5
            heading = minimum = maximum = None
    return kept


def simplify_stroke(points, tool, **tolerances):
    """Make a new outer list of retained original rows; never mutate samples."""
    return [points[index] for index in retained_indices(points, tool, **tolerances)]
