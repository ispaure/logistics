from commonUtils.ui import pyside

from features.flight_sim import actions


def display_flight_sim(dialog_obj):
    """
    Display Flight Sim Tab things
    """

    panel = pyside.create_frame(dialog_obj, pyside.QRect(10, 10, 675, 150))
    pyside.Label('M3 Max: ', panel, pyside.QRect(10, 5, 350, 20))

    pyside.button(
        'Preset: Standalone',
        panel,
        pyside.QRect(10, 25, 140, 30),
        actions.set_xp12_m3_max_standalone
    )
    pyside.button(
        'Preset: Flight Desk [Internal ON]',
        panel,
        pyside.QRect(155, 25, 250, 30),
        actions.set_xp12_m3_max_flight_desk_internal
    )
