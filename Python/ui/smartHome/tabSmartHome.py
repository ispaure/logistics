from commonUtils.ui import pyside
from commonUtils.osUtils import *


def display_smart_home(dialog_obj):
    match get_os():
        case OS.WIN:
            display_lights(dialog_obj)
        case OS.MAC:
            display_lights(dialog_obj)
        case OS.LINUX:
            display_lights(dialog_obj)


def display_lights(dialog_obj):
    """
    Display things to control lights
    """
    import wrappers.philipsHueWrapper as philipsHueWrapper

    def display_room(line_name, line_height, panel):
        pyside.Label(str(line_name + ':'), panel, pyside.QRect(10, line_height + 5, 260, 13))
        pyside.button('OFF', panel, pyside.QRect(100, line_height, 50, 20),
                      philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': False})
        pyside.button('1%', panel, pyside.QRect(155, line_height, 50, 20),
                      philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Brightness': 0})
        pyside.button('50%', panel, pyside.QRect(210, line_height, 50, 20),
                      philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Brightness': 127})
        pyside.button('100%', panel, pyside.QRect(265, line_height, 50, 20),
                      philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Brightness': 255})
        pyside.button('ON', panel, pyside.QRect(320, line_height, 50, 20),
                      philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True})
        pyside.button('R', panel, pyside.QRect(375, line_height, 20, 20),
                      philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Red'})
        pyside.button('O', panel, pyside.QRect(400, line_height, 20, 20),
                      philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Orange'})
        pyside.button('Y', panel, pyside.QRect(425, line_height, 20, 20),
                      philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Yellow'})
        pyside.button('G', panel, pyside.QRect(450, line_height, 20, 20),
                      philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Green'})
        pyside.button('A', panel, pyside.QRect(475, line_height, 20, 20),
                      philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Aqua'})
        pyside.button('B', panel, pyside.QRect(500, line_height, 20, 20),
                      philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Blue'})
        pyside.button('P', panel, pyside.QRect(525, line_height, 20, 20),
                      philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Purple'})
        pyside.button('M', panel, pyside.QRect(550, line_height, 20, 20),
                      philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Magenta'})
        pyside.button('W', panel, pyside.QRect(575, line_height, 20, 20),
                      philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'White'})

    # LIGHTS
    panel = pyside.create_frame(dialog_obj, pyside.QRect(10, 10, 675, 150))
    pyside.button('Connect Bridge', panel, pyside.QRect(550, 5, 120, 20), philipsHueWrapper.connect_bridge)
    pyside.Label('LIGHTS: ', panel, pyside.QRect(10, 10, 120, 13))

    # Living Room
    display_room(line_name='Living Room', line_height=40, panel=panel)

    # Bedroom
    display_room(line_name='Bedroom', line_height=78, panel=panel)

    # Kitchen
    display_room(line_name='Kitchen', line_height=112, panel=panel)