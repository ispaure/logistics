from typing import *
import math


class Vector2D:
    def __init__(self, direction: float, magnitude: float):
        """
        Vector2D
        :param direction: Direction of the vector in degrees (0 to 360)
        :param magnitude: Magnitude of the vector
        """
        self.direction = direction
        self.magnitude = magnitude


def calculate_net_vector_2d_direction(vector_a: Vector2D, vector_b: Vector2D):
    """
    Calculate the net resulting direction from two vectors in 360 degrees.
    :param vector_a: First Vector
    :param vector_b: Second Vector
    """
    # Convert directions to radians
    rad1 = math.radians(vector_a.direction)
    rad2 = math.radians(vector_b.direction)

    # Calculate the x and y components of each vector
    x1 = vector_a.magnitude * math.sin(rad1)
    y1 = vector_a.magnitude * math.cos(rad1)

    x2 = vector_b.magnitude * math.sin(rad2)
    y2 = vector_b.magnitude * math.cos(rad2)

    # Compute the resultant vector components
    x_result = x1 + x2
    y_result = y1 + y2

    # Calculate the resulting direction in radians
    result_angle_rad = math.atan2(x_result, y_result)

    # Convert the result back to degrees and normalize to 0-360
    result_angle_deg = (math.degrees(result_angle_rad) + 360) % 360

    return result_angle_deg


def calculate_net_vector2d_magnitude(vector_a, vector_b):
    # Convert directions to radians
    direction_a_rad = math.radians(vector_a.direction)
    direction_b_rad = math.radians(vector_b.direction)

    # Decompose vectors into x and y components
    x_a = vector_a.magnitude * math.cos(direction_a_rad)
    y_a = vector_a.magnitude * math.sin(direction_a_rad)
    x_b = vector_b.magnitude * math.cos(direction_b_rad)
    y_b = vector_b.magnitude * math.sin(direction_b_rad)

    # Sum components
    x_net = x_a + x_b
    y_net = y_a + y_b

    # Calculate resultant magnitude (net speed)
    net_speed = math.sqrt(x_net ** 2 + y_net ** 2)
    return net_speed


def invert_direction(direction):

    # Invert Direction
    inv_direction = direction + 180

    # Resolve if not between 0 and 360
    if inv_direction < 0:
        return inv_direction + 360
    elif inv_direction > 360:
        return inv_direction - 360
    else:
        return inv_direction


def is_number(input):
    for char in input:
        if char not in '0123456789.':
            return False
    return True
