import phue

from commonUtils.debugUtils import print_debug_msg
from features.smart_home import configuration


show_verbose = True

COLOR_PRESETS = {
    'Red': (0, 254),
    'Orange': (5281, 254),
    'Yellow': (10000, 254),
    'Green': (23705, 254),
    'Aqua': (39358, 254),
    'Blue': (46014, 254),
    'Purple': (50800, 254),
    'Magenta': (59526, 254),
    'White': (0, 0)
}


def set_group_prop_from_arg_dict(arg_dict):
    """
    Set Philips Hue group properties from a dictionary of arguments.
    """
    group_name = arg_dict['Room']

    # Set State
    if 'State' in arg_dict:
        set_group_state(group_name=group_name, state=arg_dict['State'])

    # Set Brightness
    if 'Brightness' in arg_dict:
        set_group_brightness(group_name=group_name, brightness=arg_dict['Brightness'])

    # Manually set Hue and Saturation
    if 'Hue' in arg_dict and 'Saturation' in arg_dict:
        set_group_color(group_name=group_name, hue=arg_dict['Hue'], saturation=arg_dict['Saturation'])

    # Set Hue/Saturation from a named color preset
    if 'Color' in arg_dict:
        color = arg_dict['Color']

        if color in COLOR_PRESETS:
            hue, saturation = COLOR_PRESETS[color]
            set_group_color(group_name=group_name, hue=hue, saturation=saturation)


def connect_bridge():
    get_bridge().connect()


def get_bridge():
    return phue.Bridge(get_bridge_address())


def get_bridge_address():
    return configuration.get_philips_hue_bridge_address()


def get_group_id_from_name(name):
    # Get bridge
    bridge = get_bridge()

    # Get all groups
    groups = bridge.get_group()

    for group in groups:
        if name == groups[group]['name']:
            print_debug_msg(f'Found group id matching "{name}"! It is {group}', show_verbose)
            return group

    # If hasn't returned yet, couldn't find any
    print_debug_msg(f'Did not find group id matching "{name}"!', show_verbose)
    return False


def set_group_state(group_name, state):
    """
    Set the lights to be switched on or off in group.

    :param group_name: Group Name
    :type group_name: str
    :param state: True is switched on, False is switched off
    :type state: bool
    """
    # Get bridge to interact with it
    bridge = get_bridge()

    # Get group id for the group name
    group_id = int(get_group_id_from_name(group_name))

    # Set the state on group id
    bridge.set_group(group_id, 'on', state)


def set_group_brightness(group_name, brightness):
    """
    Set the lights intensity level.

    :param group_name: Group Name
    :type group_name: str
    :param brightness: Intensity of light (0 to 254)
    :type brightness: int
    """
    # Get bridge to interact with it
    bridge = get_bridge()

    # Get group id for the group name
    group_id = int(get_group_id_from_name(group_name))

    # Set the brightness on group id
    bridge.set_group(group_id, 'bri', brightness)


def set_group_color(group_name, hue, saturation):
    """
    Set the lights color.

    :param group_name: Group Name
    :type group_name: str
    :param hue: Hue of light
    :type hue: int
    :param saturation: Saturation of light (0 to 254)
    :type saturation: int
    """
    # Get bridge to interact with it
    bridge = get_bridge()

    # Get group id for the group name
    group_id = int(get_group_id_from_name(group_name))

    # Set hue and saturation on group id
    bridge.set_group(group_id, 'hue', hue)
    bridge.set_group(group_id, 'sat', saturation)
