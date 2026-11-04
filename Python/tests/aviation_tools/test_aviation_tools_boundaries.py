"""Behavioral regressions owned by this feature."""
import unittest
from commonUtils.testing.stages import TestStage
from features.aviation_tools.mathUtils.flightUtils import Coordinate, MagneticDeviation, distance_from_coords, magnetic_course

TEST_STAGE = TestStage.REGRESSION


class AviationBoundaryTests(unittest.TestCase):
    def test_distance_and_course_boundaries(self):
        point = Coordinate(42.12, -73.23)
        self.assertAlmostEqual(distance_from_coords(point, point), 0, places=3)
        self.assertEqual(magnetic_course(355, MagneticDeviation(10, 'west')), 5)
        for coordinates in ((91, 0), (0, 181), (float('nan'), 0)):
            with self.assertRaises(ValueError):
                Coordinate(*coordinates)
