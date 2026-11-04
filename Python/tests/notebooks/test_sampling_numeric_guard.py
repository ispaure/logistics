"""Degenerate arc-length arithmetic must retain new-stroke dynamics exactly."""
import math
import unittest

from commonUtils.testing.stages import TestStage
from features.notebooks.sampling import retained_indices, simplify_stroke

TEST_STAGE = TestStage.REGRESSION


class SamplingNumericGuardTests(unittest.TestCase):
    def test_positive_step_absorbed_by_accumulated_distance_keeps_every_row(self):
        points = [[0., 0., .5, 3.5], [1., 0., .5, 3.5], [2., 0., .5, 3.5]]
        points.extend([[1404. if index % 2 == 0 else 0., 0., .5, 3.5] for index in range(256)])
        distance = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))
        step = 1e-12
        self.assertGreater(step, 0)
        self.assertEqual(distance + step, distance)
        # The microscopic position changes are real, while their pressure ramp
        # is not linear. A flat numeric arc parameter cannot represent it.
        points.extend([[step, 0., .51, 3.5], [step * 2, 0., .8, 3.5], [step * 3, 0., .9, 3.5]])
        before = [list(point) for point in points]
        self.assertEqual(retained_indices(points, 17), list(range(len(points))))
        result = simplify_stroke(points, 17)
        self.assertEqual(result, before)
        self.assertIsNot(result, points)
        self.assertTrue(all(a is b for a, b in zip(result, points)))
        self.assertEqual(points, before)
