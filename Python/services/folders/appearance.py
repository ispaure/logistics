"""Canonical folder artwork for desktop and mobile.

Edit FOLDER_PATHS/FOLDER_FILLS on their 24-point grid and LOCK_LIGHT/LOCK_DARK here.
After geometry/fill/stroke edits, run mobile_build/generate_folder_icons.py to refresh
the generated mobile browser indicators in mobile/hub_icons.py.
"""

from math import cos, sin, pi

FOLDER_STROKE_WIDTH = 1.275


def _arc(cx, cy, rx, ry, start, end, steps=12):
    return tuple((cx + rx * cos(start + (end - start) * i / steps),
                  cy + ry * sin(start + (end - start) * i / steps))
                 for i in range(steps + 1))


def _rounded_rect(x, y, width, height, radius):
    points = ()
    for cx, cy, start in ((x + width - radius, y + radius, -pi / 2),
                          (x + width - radius, y + height - radius, 0),
                          (x + radius, y + height - radius, pi / 2),
                          (x + radius, y + radius, pi)):
        points += _arc(cx, cy, radius, radius, start, start + pi / 2, 6)
    return points + (points[0],)


def _grid(points):
    return tuple((x * .75, y * .75) for x, y in points)


# The approved 32-point proposal is normalized to the native 24-point grid.
_folder_outline = _grid(((3, 26), (3, 8))) + _grid(_arc(5, 8, 2, 2, pi, 1.5 * pi)) + _grid(
    ((12, 6), (15, 10), (27, 10))) + _grid(_arc(27, 12, 2, 2, -pi / 2, 0)) + _grid(((29, 26), (3, 26)))
# Balanced proportions: nearly square body, with the shackle opening outward.
_closed_shackle = _grid(((13.4, 16.7), (13.4, 14.3)) + _arc(16, 14.3, 2.6, 2.002, pi, 2 * pi) + ((18.6, 16.7),))
_open_shackle = _grid(((18.5, 16.7), (18.5, 14.3)) + _arc(21.1, 14.3, 2.6, 2.002, pi, 2 * pi) + ((23.7, 16),))

FOLDER_PATHS = {
    'cloud': (((6, 18), (3, 17), (2, 14), (3, 11), (6, 10), (7, 6), (11, 4),
               (15, 5), (17, 9), (20, 10), (22, 13), (21, 17), (18, 18), (6, 18)),),
    'folder': (_folder_outline,),
    'folder_locked': (_folder_outline, _closed_shackle),
    'folder_unlocked': (_folder_outline, _open_shackle),
}
# Each filled shape is an even-odd compound path: solid body, transparent keyhole.
_lock_body = (_grid(_rounded_rect(12, 16.7, 8, 7.5, 1.5)),
              _grid(_rounded_rect(15.25, 18.25, 1.5, 4.6, .75)))
FOLDER_FILLS = {'folder_locked': _lock_body, 'folder_unlocked': _lock_body}
LOCK_LIGHT = {'folder': '#175eab', 'folder_unlocked': '#175eab', 'folder_locked': '#a64b00'}
LOCK_DARK = {'folder': '#86b9ff', 'folder_unlocked': '#86b9ff', 'folder_locked': '#ffb86b'}
