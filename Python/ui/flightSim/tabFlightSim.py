
from commonUtils.pySideUtils import *
from flightSim import flightSimUtils

def display_flight_sim(dialog_obj):
    """
    Display Flight Sim Tab things
    """
    panel = create_frame(dialog_obj, QRect(10, 10, 675, 150))
    Label('M3 Max: ', panel, QRect(10, 5, 350, 20))
    button('Preset: Standalone', panel, QRect(10, 25, 140, 30), flightSimUtils.set_xp12_m3_max_standalone)
    button('Preset: Flight Desk [Internal ON]', panel, QRect(155, 25, 250, 30), flightSimUtils.set_xp12_m3_max_flight_desk_internal)