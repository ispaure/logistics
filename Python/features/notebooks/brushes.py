"""Paper Pro choices and measured/approximate new-stroke dynamics.

Native v6 points already contain rendered widths. These rules synthesize NEW
points only; imported ink must not have pressure or thickness applied again.
See the notebook developer guide for sources and the tablet calibration gate.
"""
import math

TOOLS = {'Ballpoint': 15, 'Fineliner': 17, 'Highlighter': 18,
         'Pencil': 14, 'Mechanical pencil': 13, 'Calligraphy': 21,
         'Marker': 16, 'Shader': 23, 'Paintbrush': 12}
# -1 is an editor choice: native Highlighter orange is 15; Shader uses RGBA.
COLORS = {'Black': 0, 'Gray': 1, 'White': 2, 'Blue': 6, 'Red': 7,
          'Green': 10, 'Yellow': 13, 'Cyan': 11, 'Magenta': 12,
          'Pink': 5, 'Orange': -1}
PALETTE = {0: '#000000', 1: '#909090', 2: '#ffffff', 3: '#fbf719',
           4: '#00ff00', 5: '#ffc0cb', 6: '#304ae0', 7: '#c23132',
           8: '#7d7d7d', 9: '#ffeb3b', 10: '#91da71', 11: '#74d2e8',
           12: '#c07fd2', 13: '#fae719', 14: '#beeafe', 15: '#ffc38c',
           16: '#c7c7c6', -1: '#ff963c'}
# Writing RGB values above are from the native color PDF, OS 3.29.0.153.
HIGHLIGHTS = {13: (255, 237, 117, 255), 10: (172, 255, 133, 255),
              5: (242, 158, 255, 255), 6: (190, 234, 254, 255),
              -1: (255, 195, 140, 255), 1: (199, 199, 198, 255)}
# UI color choices differ from the actual Highlighter native PenColor IDs.
# Keep these tool-specific: legacy pen colors 3/4/5 have other palette values.
HIGHLIGHT_IDS = {13: 3, 10: 4, 5: 5, 6: 14, -1: 15, 1: 16}
NATIVE_HIGHLIGHTS = {HIGHLIGHT_IDS[key]: rgba for key, rgba in HIGHLIGHTS.items()}
# Native ARGB definitions, converted to RGBA. Shader is NOT the writing
# palette: it has gray plus seven hues and color-specific alpha values.
SHADERS = {1: (33, 30, 28, 64), 6: (48, 74, 224, 77),
           7: (194, 49, 50, 102), 10: (145, 218, 113, 128),
           13: (250, 231, 25, 115), 11: (116, 210, 232, 102),
           12: (192, 127, 210, 128), -1: (254, 178, 0, 115)}
WIDTHS = {'Thin': 1, 'Medium': 2, 'Thick': 3}
NATIVE_SCALES = (.8705015182495117, 1.7410030364990234, 2.611504554748535)
PEN_COLORS = (0, 1, 2, 6, 7, 10, 13, 11, 12)


def profile(widths, pressure=0, exponent=1, *, colors=PEN_COLORS, **style):
    return dict(widths=widths, pressure=pressure, exponent=exponent,
                colors=colors, **style)


# November 4 Paper Pro / OS 3.29.0.153 sample: native page units, not mm.
# Constant widths and Shader saturation are directly observed. Pressure curves,
# texture, speed/tilt and calligraphy nib behavior remain approximations.
BRUSHES = {
    17: profile((2, 3.5, 5.25), family='fineliner'),
    15: profile((2.5, 3.75, 5.75), .34, 3.875, family='ballpoint'),
    14: profile((2.75, 5.25, 8), .34, family='pencil', texture=True),
    13: profile((3.5, 5.25, 7.75), family='mechanical', texture=True),
    16: profile((5.5, 6.25, 9), .25, family='marker'),
    12: profile((4.5, 8.5, 12.75), family='paintbrush',
                pressure_widths=((.25, (2, 3.5, 5.25)), (.75, (2, 3.5, 5.25)),
                                 (.85, (2.75, 5, 7)), (.95, (4, 7.75, 10.5)),
                                 (1, (4.5, 8.5, 12.75)))),
    21: profile((2.5, 4.5, 6.5), .25, family='calligraphy', directional=True, nib_angle=-math.pi / 4, nib_ratio=.25),
    # Accept old three-width commands without inventing extra firmware sizes.
    18: profile((26, 26, 26), colors=tuple(HIGHLIGHTS), family='highlighter', fixed_width=True),
    23: profile((10.75, 19.5, 28), colors=tuple(SHADERS), family='shader',
                pressure_widths=((0, (3.5, 6.5, 9.25)), (.1, (3.5, 6.5, 9.25)),
                                 (.2, (7, 13, 18.5)), (.3, (10.75, 19.5, 28)),
                                 (1, (10.75, 19.5, 28)))),
}


# Expanded PDF scenes use a different unit for the same brush size.
EXPANDED_INK_SCALE = (227 / 72) / NATIVE_SCALES[0]


def expanded_profile(brush):
    result = dict(brush, widths=tuple(width * EXPANDED_INK_SCALE for width in brush['widths']))
    if 'pressure_widths' in brush:
        result['pressure_widths'] = tuple(
            (pressure, tuple(width * EXPANDED_INK_SCALE for width in widths))
            for pressure, widths in brush['pressure_widths'])
    return result


EXPANDED_BRUSHES = {tool: expanded_profile(brush) for tool, brush in BRUSHES.items()}
EXPANDED_BRUSHES[17]['widths'] = (6.25, 12.5, 19)


def native_color(tool, color):
    if type(tool) is not int or tool not in BRUSHES or type(color) is not int or color not in BRUSHES[tool]['colors']:
        raise ValueError('Choose a color supported by this brush.')
    if tool == 18:
        return HIGHLIGHT_IDS[color], None
    if tool == 23:
        return 9, SHADERS[color]
    return color, None


def native_scale(tool, width, *, expanded=False):
    scale = NATIVE_SCALES[0 if BRUSHES[tool].get('fixed_width') else int(width) - 1]
    return scale * EXPANDED_INK_SCALE if expanded else scale


def pressure_width(brush, width, pressure):
    curve = brush.get('pressure_widths')
    if not curve:
        return brush['widths'][width - 1] * (1 - brush['pressure'] + brush['pressure'] * pressure ** brush['exponent'])
    if pressure <= curve[0][0]:
        return curve[0][1][width - 1]
    for (start, before), (end, after) in zip(curve, curve[1:]):
        if pressure <= end:
            fraction = (pressure - start) / (end - start)
            return before[width - 1] + fraction * (after[width - 1] - before[width - 1])
    return curve[-1][1][width - 1]


def stroke_points(points, tool, width, *, expanded=False):
    brush = (EXPANDED_BRUSHES if expanded else BRUSHES)[tool]
    result = []
    for index, (x, y, pressure) in enumerate(points):
        value = pressure_width(brush, width, pressure)
        if brush.get('directional'):
            before = points[index - 1] if index else points[min(1, len(points) - 1)]
            angle = math.atan2(y - before[1], x - before[0])
            delta = angle - brush['nib_angle']
            value *= math.hypot(math.sin(delta), brush['nib_ratio'] * math.cos(delta))
        # Match the codec's quarter-unit precision in the live preview too.
        result.append([x, y, pressure, max(.25, math.floor(value * 4 + .5) / 4)])
    return result
