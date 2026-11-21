"""
UI contributions exposed by the Logistics Flight Simulator feature.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from features.contributions import DebugActionContribution, Feature, SettingsContribution
from pathlib import Path
from features.flight_sim import actions


def get_contributions() -> Feature:
    """Return UI contributions provided by Flight Simulator."""

    return Feature(
        id='flight_sim', label='X-Plane Presets',
        settings=[SettingsContribution('Installation', 'installation', config_files=(Path(__file__).with_name('config.ini'),))],
        debug_actions=[
            DebugActionContribution(
                name='X-Plane 12: M3 Max Standalone',
                callback=actions.set_xp12_m3_max_standalone,
                destructive=True,
                order=10
            ),
            DebugActionContribution(
                name='X-Plane 12: M3 Max Flight Desk [Internal ON]',
                callback=actions.set_xp12_m3_max_flight_desk_internal,
                destructive=True,
                order=20
            ),
            DebugActionContribution(
                name='X-Plane 12: M3 Max Office',
                callback=actions.set_xp12_m3_max_office,
                destructive=True,
                order=30
            ),
        ]
    )
