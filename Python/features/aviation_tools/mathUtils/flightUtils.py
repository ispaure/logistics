import math
from commonUtils.logUtils import *
from commonUtils import logUtils
from features.aviation_tools.mathUtils.mathStuff import *


class Coordinate:
    """
    A set of world coordinates as float numbers
    """
    def __init__(self, latitude: float, longitude: float):
        self.latitude = float(latitude)
        self.longitude = float(longitude)

    def get_info(self):
        return f'{self.latitude}, {self.longitude}'


class MagneticDeviation:
    def __init__(self, amount: float, direction: str):
        self.amount = float(amount)
        self.direction = str.lower(direction)

    def get_info(self):
        info_str = f'{self.amount} {self.direction} '
        if str.lower(self.direction) == 'west':
            info_str += f'(+{self.amount})'
        else:
            info_str += f'(-{self.amount})'
        return info_str

    def net_result(self):
        if str.lower(self.direction) == 'west':
            return self.amount
        elif str.lower(self.direction) == 'east':
            return -self.amount


def distance_from_coords(coordinate_a: Coordinate, coordinate_b: Coordinate) -> float:
    """
    Get the distance between two points on the globe
    :param coordinate_a:
    :param coordinate_b:
    :param round_digit:
    :return: Distance (in nautical miles)
    """
    msg = f'Calculate coordinates between: ({coordinate_a.latitude}, {coordinate_a.longitude}) and ({coordinate_b.latitude}, {coordinate_b.longitude})'
    log_msg(msg)
    result = 3440.065 * math.acos(math.cos(math.radians(90 - coordinate_b.latitude)) * math.cos(math.radians(90 - coordinate_a.latitude)) +
                                  math.sin(math.radians(90 - coordinate_b.latitude)) * math.sin(math.radians(90 - coordinate_a.latitude))
                                  * math.cos(math.radians(coordinate_b.longitude - coordinate_a.longitude)))
    return float(result)


def true_course_from_coords(coordinate_a: Coordinate, coordinate_b: Coordinate) -> float:
    """
    Get the true course between two points on the globe
    :param coordinate_a: Point of origin
    :param coordinate_b: Point of destination
    :param round_digit: Rounding of the final result
    :return: True Course (in degrees)
    """
    msg = f'Calculate true course between: ({coordinate_a.latitude}, {coordinate_a.longitude}) and ({coordinate_b.latitude}, {coordinate_b.longitude})'
    log_msg(msg)

    # Convert latitude and longitude from degrees to radians
    lat1 = math.radians(coordinate_a.latitude)
    lon1 = math.radians(coordinate_a.longitude)
    lat2 = math.radians(coordinate_b.latitude)
    lon2 = math.radians(coordinate_b.longitude)

    # Calculate the differences
    delta_lon = lon2 - lon1

    # Calculate the true course using the formula
    x = math.sin(delta_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    initial_bearing = math.atan2(x, y)

    # Convert the result from radians to degrees and normalize to 0-360
    initial_bearing = math.degrees(initial_bearing)
    true_course = (initial_bearing + 360) % 360

    return float(true_course)


def magnetic_course(true_course: float, magnetic_deviation: MagneticDeviation) -> float:
    """
    Get the Magnetic Course
    :param true_course: True course direction (in degrees)
    :param magnetic_deviation: MagneticDeviation class
    :return: Magnetic Course (in degrees)
    """
    if magnetic_deviation.direction == 'west':
        return true_course + magnetic_deviation.amount
    elif magnetic_deviation.direction == 'east':
        return true_course - magnetic_deviation.amount
    else:
        raise ValueError('Magnetic deviation direction must be east or west.')


def flight_altitude_rule(magnetic_course: float):
    """
    Get the altitude rule (0-180> Odd + 500, 180-360 > Even + 500)
    :param magnetic_course:
    :return:
    """
    if magnetic_course < 180:
        return 'Odd + 500FT'
    else:
        return 'Even + 500FT'


def ktas_to_kias(ktas, altitude):
    """
    Converts KTAS (Knots True Airspeed) to KIAS (Knots Indicated Airspeed)
    based on altitude in feet under ISA conditions.

    :param ktas: True airspeed in knots
    :param altitude: Altitude in feet
    :param round_digit: How many decimal digits to keep
    :return: Indicated airspeed in knots
    """
    # Simplified density ratios for altitudes
    if altitude == 2000:
        density_ratio = 0.952  # Approximation for 2000 ft
    else:
        # If other altitudes are needed, you could add a formula here
        raise ValueError("Density ratio needs to be approximated for this altitude.")

    # Calculate KIAS
    kias = ktas * math.sqrt(density_ratio)
    return float(kias)


def wind_correction_angle(true_course, true_airspeed, wind_direction, wind_speed):
    """
    Calculate the WCA (Wind Correction Angle) ; Dérive in French
    :param true_course: True Course (TCrs) (Plane is going towards) -- in Degrees (0-360)
    :param true_airspeed: True Airspeed (KTAS)
    :param wind_direction: Wind Direction (Wind is coming from) -- in Degrees (0-360)
    :param wind_speed: Wind Speed (KT)
    :return: WCA
    :rtype: float
    """

    # Calculate the true heading
    true_heading_result = true_heading(true_course, true_airspeed, wind_direction, wind_speed)

    # Return WCA
    return float(true_heading_result - true_course)


def true_heading(true_course, true_airspeed, wind_direction, wind_speed):
    """
    Calculate the True Heading
    :param true_course: True Course (TCrs) (Plane is going towards) -- in Degrees (0-360)
    :param true_airspeed: True Airspeed (KTAS)
    :param wind_direction: Wind Direction (Wind is coming from) -- in Degrees (0-360)
    :param wind_speed: Wind Speed (KT)
    :return: True Heading
    :rtype: float
    """
    # Calculate the true heading
    true_heading_result = calculate_net_vector_2d_direction(Vector2D(true_course, true_airspeed), Vector2D(wind_direction, wind_speed))

    # Return true heading
    return float(true_heading_result)


def ground_speed(true_course, true_airspeed, wind_direction, wind_speed):
    """
    Calculate the Ground Speed (GS)
    :param true_course: True Course (TCrs) (Plane is going towards) -- in Degrees (0-360)
    :param true_airspeed: True Airspeed (KTAS)
    :param wind_direction: Wind Direction (Wind is coming from) -- in Degrees (0-360)
    :param wind_speed: Wind Speed (KT)
    :return: Ground Speed
    :rtype: float
    """
    # Inverted wind direction
    inv_wind_direction = invert_direction(wind_direction)

    # Calculate the ground speed
    ground_speed_result = calculate_net_vector2d_magnitude(Vector2D(true_course, true_airspeed), Vector2D(inv_wind_direction, wind_speed))

    # Return true heading
    return float(ground_speed_result)


def magnetic_heading(true_heading: float, magnetic_deviation: MagneticDeviation):
    return true_heading + magnetic_deviation.net_result()
