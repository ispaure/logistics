# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"


def convert_isa_str_to_temp(isa: str) -> float:
    """
    Converts the ISA reading to its equivalent temperature
    """
    if str.lower(isa) == 'isa':
        return 15
    elif str.lower(isa) == 'isa-20':
        return 15 - 20
    elif str.lower(isa) == 'isa+20':
        return 15 + 20
    else:
        msg = f'Temperature reading is invalid. Expected: "ISA", "ISA-20" or "ISA+20" (case-intensitive)'
        raise ValueError(msg)
        return None


def get_temperature_at_altitude(ground_temperature: float, altitude: float):
    """
    Get the temperature at altitude from the ground temperature and altitude.
    :param ground_temperature: Temperature ASL (in Celsius)
    :param altitude: Altitude ASL (in FT)
    """
    return ground_temperature - 2 / 1000 * altitude
