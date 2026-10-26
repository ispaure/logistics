"""Paper Pro/Move choices and approximate new-stroke dynamics.

Native v6 points already contain rendered widths. These rules synthesize NEW
points only; imported ink must not have pressure or thickness applied again.
See the notebook developer guide for sources and the tablet calibration gate.
"""
import math

TOOLS = {'Ballpoint': 15, 'Fineliner': 17, 'Highlighter': 18,
         'Pencil': 14, 'Mechanical pencil': 13, 'Calligraphy': 21,
         'Marker': 16, 'Shader': 23, 'Paintbrush': 12}
# -1 is an editor choice, never a native PenColor. Orange uses HIGHLIGHT + RGBA.
COLORS = {'Black': 0, 'Gray': 1, 'White': 2, 'Blue': 6, 'Red': 7,
          'Green': 10, 'Yellow': 13, 'Cyan': 11, 'Magenta': 12,
          'Pink': 5, 'Orange': -1}
PALETTE = {0: '#000000', 1: '#909090', 2: '#ffffff', 3: '#fbf719',
           4: '#00ff00', 5: '#ffc0cb', 6: '#4e69c9', 7: '#b33e39',
           8: '#7d7d7d', 9: '#ffeb3b', 10: '#a1d87d', 11: '#8bd0e5',
           12: '#b782cd', 13: '#f7e851', -1: '#ff963c'}
HIGHLIGHTS = {13: (255, 237, 117, 255), 10: (172, 255, 133, 255),
              5: (242, 158, 255, 255), 6: (190, 234, 254, 255),
              -1: (255, 195, 140, 255), 1: (199, 199, 198, 255)}
# Native ARGB definitions, converted to RGBA. Shader is NOT the writing
# palette: it has gray plus seven hues and color-specific alpha values.
SHADERS = {1: (33, 30, 28, 64), 6: (48, 74, 224, 77),
           7: (194, 49, 50, 102), 10: (145, 218, 113, 128),
           13: (250, 231, 25, 115), 11: (116, 210, 232, 102),
           12: (192, 127, 210, 128), -1: (254, 178, 0, 115)}
WIDTHS = {'Thin': 1, 'Medium': 2, 'Thick': 3}
PEN_COLORS = (0, 1, 2, 6, 7, 10, 13, 11, 12)


def profile(widths, pressure=0, exponent=1, *, colors=PEN_COLORS, **style):
    return dict(widths=widths, pressure=pressure, exponent=exponent,
                colors=colors, **style)


# Nominal widths are canvas units, not mm. They are rendering approximations,
# not a claim that every firmware uses these exact device-computed widths.
BRUSHES = {
    17: profile((1, 2, 4), family='fineliner'),
    15: profile((1, 2, 4), .65, 1.2, family='ballpoint'),
    14: profile((2, 4, 8), .85, 1.1, family='pencil', texture=True),
    13: profile((1, 1.5, 2), family='mechanical', texture=True),
    16: profile((3, 6, 10), .25, family='marker'),
    12: profile((4, 8, 16), .9, 1.7, family='paintbrush'),
    21: profile((3, 6, 12), .25, family='calligraphy', directional=True, nib_angle=-math.pi / 4, nib_ratio=.25),
    18: profile((15, 30, 60), colors=tuple(HIGHLIGHTS), family='highlighter'),
    23: profile((15, 30, 60), .7, colors=tuple(SHADERS), family='shader'),
}


def native_color(tool, color):
    if type(tool) is not int or tool not in BRUSHES or type(color) is not int or color not in BRUSHES[tool]['colors']:
        raise ValueError('Choose a color supported by this brush.')
    if tool == 18:
        return 9, HIGHLIGHTS[color]
    if tool == 23:
        return 9, SHADERS[color]
    return color, None


def stroke_points(points, tool, width):
    brush = BRUSHES[tool]
    base = brush['widths'][width - 1]
    result = []
    for index, (x, y, pressure) in enumerate(points):
        value = base * (1 - brush['pressure'] + brush['pressure'] * pressure ** brush['exponent'])
        if brush.get('directional'):
            before = points[index - 1] if index else points[min(1, len(points) - 1)]
            angle = math.atan2(y - before[1], x - before[0])
            delta = angle - brush['nib_angle']
            value *= math.hypot(math.sin(delta), brush['nib_ratio'] * math.cos(delta))
        # Match the codec's quarter-unit precision in the live preview too.
        result.append([x, y, pressure, max(.25, math.floor(value * 4 + .5) / 4)])
    return result
