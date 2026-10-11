"""Validated Hue group commands; callers decide how to present failures."""
import phue
from features.smart_home import configuration

COLOR_PRESETS = {
    'Red': (0, 254), 'Orange': (5281, 254), 'Yellow': (10000, 254),
    'Green': (23705, 254), 'Aqua': (39358, 254), 'Blue': (46014, 254),
    'Purple': (50800, 254), 'Magenta': (59526, 254), 'White': (0, 0),
}


def get_bridge_address():
    address = configuration.get_philips_hue_bridge_address()
    if not address or not address.strip():
        raise ValueError('Set the Hue bridge address in Smart Home settings.')
    return address.strip()


def get_bridge():
    return phue.Bridge(get_bridge_address())


def connect_bridge():
    get_bridge().connect()
    return True


def _group_id(bridge, name):
    matches = [key for key, group in bridge.get_group().items() if group['name'] == name]
    if len(matches) != 1 or not str(matches[0]).isdecimal() or int(matches[0]) <= 0:
        raise ValueError(f'Hue room is missing or ambiguous: {name}')
    return int(matches[0])


def get_group_id_from_name(name):
    return _group_id(get_bridge(), name)


def get_rooms():
    return tuple(sorted({group['name'] for key, group in get_bridge().get_group().items()
                         if str(key).isdecimal() and int(key) > 0}))


def _integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be an integer from {minimum} to {maximum}.')
    return value


def set_group_prop_from_arg_dict(arguments):
    properties = {}
    if 'State' in arguments:
        if type(arguments['State']) is not bool:
            raise ValueError('State must be True or False.')
        properties['on'] = arguments['State']
    if 'Brightness' in arguments:
        properties['bri'] = _integer(arguments['Brightness'], 0, 254, 'Brightness')
    if ('Hue' in arguments) != ('Saturation' in arguments):
        raise ValueError('Supply both hue and saturation.')
    if 'Hue' in arguments:
        properties['hue'] = _integer(arguments['Hue'], 0, 65535, 'Hue')
        properties['sat'] = _integer(arguments['Saturation'], 0, 254, 'Saturation')
    if 'Color' in arguments:
        try:
            properties['hue'], properties['sat'] = COLOR_PRESETS[arguments['Color']]
        except KeyError:
            raise ValueError(f"Unknown color: {arguments['Color']}") from None
    if not properties:
        raise ValueError('Choose a light property to change.')
    bridge = get_bridge()
    group = _group_id(bridge, arguments['Room'])
    responses = bridge.set_group(group, properties)
    for response in responses or ():
        for item in response if isinstance(response, list) else [response]:
            if isinstance(item, dict) and 'error' in item:
                raise RuntimeError(str(item['error']))
    return True


def set_group_state(group_name, state):
    return set_group_prop_from_arg_dict({'Room': group_name, 'State': state})


def set_group_brightness(group_name, brightness):
    return set_group_prop_from_arg_dict({'Room': group_name, 'Brightness': brightness})


def set_group_color(group_name, hue, saturation):
    return set_group_prop_from_arg_dict({'Room': group_name, 'Hue': hue, 'Saturation': saturation})
