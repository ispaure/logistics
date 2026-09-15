import config as config
import phue
from commonUtils import configUtils
from commonUtils.debugUtils import print_debug_msg as print_debug_msg


show_verbose = True


# ARG DICTS (FROM UI, NEED TO CONVERT TO ARGUMENTS TO EXECUTE FUNCTION PROPERLY)
def set_group_prop_from_arg_dict(arg_dict):

    # Set State
    if 'State' in arg_dict.keys():
        set_group_state(group_name=arg_dict['Room'], state=arg_dict['State'])

    # Set Brightness
    if 'Brightness' in arg_dict.keys():
        set_group_brightness(group_name=arg_dict['Room'], brightness=arg_dict['Brightness'])

    # Manually set Hue and Saturation
    if 'Hue' in arg_dict.keys() and 'Sat' in arg_dict.keys():
        set_group_color(group_name=arg_dict['Room'], hue=arg_dict['Hue'], saturation=arg_dict['Saturation'])

    # Set Hue/Saturation by name with one of the presets here (simpler than remembering values)
    if 'Color' in arg_dict.keys():
        if arg_dict['Color'] == 'Red':
            set_group_color(group_name=arg_dict['Room'], hue=0, saturation=254)
        if arg_dict['Color'] == 'Orange':
            set_group_color(group_name=arg_dict['Room'], hue=5281, saturation=254)
        if arg_dict['Color'] == 'Yellow':
            set_group_color(group_name=arg_dict['Room'], hue=10000, saturation=254)
        if arg_dict['Color'] == 'Green':
            set_group_color(group_name=arg_dict['Room'], hue=23705, saturation=254)
        if arg_dict['Color'] == 'Aqua':
            set_group_color(group_name=arg_dict['Room'], hue=39358, saturation=254)
        if arg_dict['Color'] == 'Blue':
            set_group_color(group_name=arg_dict['Room'], hue=46014, saturation=254)
        if arg_dict['Color'] == 'Purple':
            set_group_color(group_name=arg_dict['Room'], hue=50800, saturation=254)
        if arg_dict['Color'] == 'Magenta':
            set_group_color(group_name=arg_dict['Room'], hue=59526, saturation=254)
        if arg_dict['Color'] == 'White':
            set_group_color(group_name=arg_dict['Room'], hue=0, saturation=0)


# FUNCTIONS


def connect_bridge():
    get_bridge().connect()


def get_bridge():
    return phue.Bridge(get_bridge_address())


def get_bridge_address():
    return configUtils.config_section_map(config.get_config_file_path(), 'ResolveIP', 'hue-hub')


def get_group_id_from_name(name):

    # Get bridge
    bridge = get_bridge()

    # Get all groups
    groups = bridge.get_group()

    for group in groups:
        # print('\n\n')
        # print(groups[group])
        if name == groups[group]['name']:
            print_debug_msg('Found group id matching "{}"! It is {}'.format(name, str(group)), show_verbose)
            return group

    # If hasn't returned yet, couldn't find any. Throw error
    print_debug_msg('Did not found group id matching "{}"!', show_verbose)
    return False


def set_group_state(group_name, state):
    """
    Set the lights to be switched on or off in group.
    :param group_name: Group Name (must be in list)
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
    :param group_name: Group Name (must be in list)
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
    Set the lights intensity level.
    :param group_name: Group Name (must be in list)
    :type group_name: str
    :param hue: Hue of light (Integer can be a large number in 50k idk what is the max)
    :type hue: int
    :param saturation: Saturation of light (Integer from 0 to 254)
    :type saturation: int
    """

    # Get bridge to interact with it
    bridge = get_bridge()

    # Get group id for the group name
    group_id = int(get_group_id_from_name(group_name))

    # Set the hue on group id
    bridge.set_group(group_id, 'hue', hue)
    # Set the saturation on group id
    bridge.set_group(group_id, 'sat', saturation)
