
from commonUtils.pySideUtils import *
from commonUtils.osUtils import *


def display_smart_home(dialog_obj):
    match get_os():
        case OS.WIN:
            display_lights(dialog_obj)
        case OS.MAC:
            display_lights(dialog_obj)
        case OS.LINUX:
            pass


def display_lights(dialog_obj):
    """
    Display things to control lights
    """
    import wrappers.philipsHueWrapper as philipsHueWrapper

    def display_room(line_name, line_height, panel):
        Label(str(line_name + ':'), panel, QRect(10, line_height + 5, 260, 13))
        button('OFF', panel, QRect(100, line_height, 50, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': False})
        button('1%', panel, QRect(155, line_height, 50, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Brightness': 0})
        button('50%', panel, QRect(210, line_height, 50, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Brightness': 127})
        button('100%', panel, QRect(265, line_height, 50, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Brightness': 255})
        button('ON', panel, QRect(320, line_height, 50, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True})
        button('R', panel, QRect(375, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Red'})
        button('O', panel, QRect(400, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Orange'})
        button('Y', panel, QRect(425, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Yellow'})
        button('G', panel, QRect(450, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Green'})
        button('A', panel, QRect(475, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Aqua'})
        button('B', panel, QRect(500, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Blue'})
        button('P', panel, QRect(525, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Purple'})
        button('M', panel, QRect(550, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Magenta'})
        button('W', panel, QRect(575, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'White'})

    # LIGHTS
    panel = create_frame(dialog_obj, QRect(10, 10, 675, 150))
    button('Connect Bridge', panel, QRect(550, 5, 120, 20), philipsHueWrapper.connect_bridge)
    Label('LIGHTS: ', panel, QRect(10, 10, 120, 13))

    # Living Room
    display_room(line_name='Living Room', line_height=40, panel=panel)

    # Bedroom
    display_room(line_name='Bedroom', line_height=78, panel=panel)

    # Kitchen
    display_room(line_name='Kitchen', line_height=112, panel=panel)