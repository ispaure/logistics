"""Independent reconstruction checks for new-stroke sample compaction.

Fixtures are original synthetic geometry. These tests do not infer tablet sample
rates from a spatial worksheet or compare strokes using undocumented timestamps.
"""
from collections.abc import Sequence
from copy import deepcopy
import inspect
import math
import random
import struct
import unittest

from commonUtils.testing.stages import TestStage
from features.notebooks.brushes import BRUSHES, stroke_points
from features.notebooks.sampling import retained_indices as sampled_indices, simplify_stroke

TEST_STAGE = TestStage.REGRESSION
POSITION_ERROR = .125
PRESSURE_ERROR = 1 / 255
WIDTH_ERROR = .0625


def retained_indices(original, reduced):
    """Resolve retained source rows without ambiguity at repeated coordinates."""
    indices, cursor = [], 0
    for row in reduced:
        while cursor < len(original) and original[cursor] is not row:
            cursor += 1
        if cursor == len(original):
            raise AssertionError('Compaction must retain ordered original rows, without synthesizing dynamics')
        indices.append(cursor)
        cursor += 1
    return indices


def reconstruction_errors(original, reduced):
    """Rebuild every removed point from retained endpoints and original arc length."""
    indices = retained_indices(original, reduced)
    if not original:
        return dict(position=0., projection=0., pressure=0., encoded_pressure=0., width=0.,
                    projection_pressure=0., projection_encoded_pressure=0., projection_width=0.)
    if not indices or indices[0] != 0 or indices[-1] != len(original) - 1:
        raise AssertionError('Original first and last samples must survive')
    distance = [0.]
    for before, after in zip(original, original[1:]):
        distance.append(distance[-1] + math.hypot(after[0] - before[0], after[1] - before[1]))
    errors = dict(position=0., projection=0., pressure=0., encoded_pressure=0., width=0.,
                  projection_pressure=0., projection_encoded_pressure=0., projection_width=0.)
    for left, right in zip(indices, indices[1:]):
        start, end = original[left], original[right]
        length = distance[right] - distance[left]
        for index in range(left + 1, right):
            point = original[index]
            if not length:
                if point[2:] != start[2:] or point[2:] != end[2:]:
                    raise AssertionError('Coincident pen dynamics cannot be reconstructed from position')
                continue
            fraction = (distance[index] - distance[left]) / length
            interpolated = [a + (b - a) * fraction for a, b in zip(start, end)]
            errors['position'] = max(errors['position'], math.hypot(point[0] - interpolated[0], point[1] - interpolated[1]))
            dx, dy = end[0] - start[0], end[1] - start[1]
            square = dx * dx + dy * dy
            projection = max(0, min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / square)) if square else 0
            errors['projection'] = max(errors['projection'], math.hypot(
                point[0] - start[0] - projection * dx, point[1] - start[1] - projection * dy))
            projected = [a + (b - a) * projection for a, b in zip(start, end)]
            errors['projection_pressure'] = max(errors['projection_pressure'], abs(point[2] - projected[2]))
            encoded_projection = (round(start[2] * 255) * (1 - projection) + round(end[2] * 255) * projection) / 255
            errors['projection_encoded_pressure'] = max(errors['projection_encoded_pressure'],
                                                       abs(round(point[2] * 255) / 255 - encoded_projection))
            errors['projection_width'] = max(errors['projection_width'], abs(point[3] - projected[3]))
            errors['pressure'] = max(errors['pressure'], abs(point[2] - interpolated[2]))
            encoded = (round(start[2] * 255) * (1 - fraction) + round(end[2] * 255) * fraction) / 255
            errors['encoded_pressure'] = max(errors['encoded_pressure'], abs(round(point[2] * 255) / 255 - encoded))
            errors['width'] = max(errors['width'], abs(point[3] - interpolated[3]))
    return errors


def area(points):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:])) / 2


class WorkBudget:
    def __init__(self, maximum):
        self.maximum, self.reads = maximum, 0

    def touch(self):
        self.reads += 1
        if self.reads > self.maximum:
            raise AssertionError('Sample inspection exceeded the linear-work budget')


class CountedPoint(Sequence):
    def __init__(self, values, budget):
        self.values, self.budget = values, budget

    def __len__(self):
        return 4

    def __getitem__(self, index):
        self.budget.touch()
        return self.values[index]


class StrokeSamplingTests(unittest.TestCase):
    def compact(self, original, tool=14):
        snapshot = deepcopy(original)
        reduced = simplify_stroke(original, tool, position_tolerance=POSITION_ERROR,
                                  pressure_tolerance=PRESSURE_ERROR, width_tolerance=WIDTH_ERROR)
        self.assertEqual(original, snapshot, 'Compaction mutated input stroke geometry')
        errors = reconstruction_errors(original, reduced)
        self.assertLessEqual(errors['position'], POSITION_ERROR + 1e-9)
        self.assertLessEqual(errors['projection'], POSITION_ERROR + 1e-9)
        self.assertLessEqual(errors['pressure'], PRESSURE_ERROR + 1e-12)
        self.assertLessEqual(errors['encoded_pressure'], PRESSURE_ERROR + 1e-12)
        self.assertLessEqual(errors['width'], WIDTH_ERROR + 1e-12)
        self.assertLessEqual(errors['projection_pressure'], PRESSURE_ERROR + 1e-12)
        self.assertLessEqual(errors['projection_encoded_pressure'], PRESSURE_ERROR + 1e-12)
        self.assertLessEqual(errors['projection_width'], WIDTH_ERROR + 1e-12)
        return reduced

    def test_public_defaults_match_the_reviewed_native_precision_contract(self):
        parameters = inspect.signature(sampled_indices).parameters
        self.assertEqual(parameters['position_tolerance'].default, POSITION_ERROR)
        self.assertEqual(parameters['pressure_tolerance'].default, PRESSURE_ERROR)
        self.assertEqual(parameters['width_tolerance'].default, WIDTH_ERROR)
        self.assertEqual(parameters['native_x_origin'].default, 702.)

    def test_all_brushes_and_widths_obey_independent_reconstruction_bounds(self):
        samples = [[20 + i * .2, 100 + math.sin(i / 75) * 2, .1 + i / 600]
                   for i in range(401)]
        for tool in BRUSHES:
            for width in (1, 2, 3):
                with self.subTest(tool=tool, width=width):
                    original = stroke_points(samples, tool, width)
                    reduced = self.compact(original, tool)
                    if tool == 21:
                        self.assertEqual(reduced, original, 'Directional nib geometry must bypass compaction')

    def test_directional_nib_cannot_be_recovered_from_position_and_width_error_alone(self):
        # Equal stored perpendicular widths can imply different nib radii after
        # the neighbor tangent changes. Tiny geometry is not sufficient safety.
        original = [[20 + i * .05, 30 + (i % 2) * .02, .5, 3.5] for i in range(257)]
        self.assertEqual(self.compact(original, 21), original)

    def test_straight_redundancy_compacts_but_endpoints_and_raw_rows_stay_exact(self):
        original = [[20 + i / 8, 30., .200123, 3.5] for i in range(257)]
        reduced = self.compact(original, 13)
        self.assertEqual(len(reduced), 2)
        self.assertIs(reduced[0], original[0])
        self.assertIs(reduced[-1], original[-1])

    def test_dots_coincident_pressure_and_width_dynamics_are_not_lost(self):
        for original in ([[20., 30., .5, 3.5]], [[20., 30., p, w] for p, w in
                         [(.2, 2.), (.9, 4.), (.3, 2.25), (.8, 3.5), (.4, 2.5)]]):
            self.assertEqual(self.compact(original), original)

    def test_empty_pairs_and_identical_stationary_samples_have_defined_boundaries(self):
        self.assertEqual(self.compact([]), [])
        pair = [[20., 30., .5, 3.5], [21., 30., .5, 3.5]]
        self.assertEqual(self.compact(pair), pair)
        duplicate = [[20., 30., .5, 3.5] for _ in range(257)]
        reduced = self.compact(duplicate)
        self.assertEqual(len(reduced), 2)

    def test_subbyte_raw_pressure_jitter_remains_bounded_without_becoming_mandatory_extrema(self):
        original = [[20 + i * .125, 30., .4 + math.sin(i * 2) * .0003, 3.5]
                    for i in range(257)]
        self.assertEqual(len({round(point[2] * 255) for point in original}), 1)
        reduced = self.compact(original)
        self.assertLess(len(reduced), len(original) // 4)

    def test_native_flat_bin_pressure_jitter_at_capture_limit_is_redundant(self):
        original = [[20 + i * .005, 30., .4 + (.001 if i % 2 else -.001), 3.5]
                    for i in range(100_000)]
        self.assertEqual(len({round(point[2] * 255) for point in original}), 1)
        reduced = self.compact(original, 17)
        self.assertEqual(len(reduced), 2)

    def test_crossing_a_native_pressure_bin_boundary_is_not_redundant_jitter(self):
        boundary = 102.5 / 255
        original = [[20 + i * .125, 30., boundary + (1e-6 if i % 2 else -1e-6), 3.5]
                    for i in range(257)]
        self.assertEqual(len({round(point[2] * 255) for point in original}), 2)
        self.assertEqual(self.compact(original, 17), original)

    def test_native_float32_coincident_pressure_and_width_dynamics_survive(self):
        x_collision = [[x, 10., p, 3.5] for x, p in zip((1e-5, 2e-5, 3e-5), (.2, .5, .8))]
        y_collision = [[20., 40 + step, p, 3.5] for step, p in
                       zip((1e-7, 2e-7, 3e-7), (.2, .5, .8))]
        large_y_collision = [[20., 999999 + step, p, 3.5] for step, p in
                             zip((.001, .002, .003), (.2, .5, .8))]
        width_collision = [[x, 10., .5, width] for x, width in
                           zip((1e-5, 2e-5, 3e-5), (.25, .5, .75))]
        for original in (x_collision, y_collision, large_y_collision, width_collision):
            encoded_xy = {(struct.pack('<f', p[0] - 702), struct.pack('<f', p[1])) for p in original}
            self.assertEqual(len(encoded_xy), 1)
            self.assertNotEqual(original[0][:2], original[1][:2])
            self.assertEqual(self.compact(original, 17), original)
        # The optional origin must model the actual X subtraction performed by
        # the native writer, rather than assuming every float32 uses page X.
        unshifted = simplify_stroke(x_collision, 17, native_x_origin=0)
        self.assertEqual(len(unshifted), 2)

    def test_zero_tolerances_and_invalid_inputs_do_not_silently_widen_the_contract(self):
        straight = [[20 + i * .25, 30., .5, 3.5] for i in range(65)]
        exact = simplify_stroke(straight, 14, position_tolerance=0,
                                pressure_tolerance=0, width_tolerance=0)
        self.assertTrue(all(value == 0 for value in reconstruction_errors(straight, exact).values()))
        for invalid in (-1, float('nan'), float('inf'), True, None, '0.125'):
            with self.subTest(tolerance=invalid), self.assertRaises(ValueError):
                simplify_stroke(straight, 14, position_tolerance=invalid)
        for invalid in ([20, 30, .5], [20, 30, float('nan'), 3.5], [20, 30, 1.01, 3.5],
                        [20, 30, .5, -1], [True, 30, .5, 3.5]):
            with self.subTest(point=invalid), self.assertRaises(ValueError):
                simplify_stroke([invalid], 14)
        for invalid in (float('nan'), float('inf'), True, None, '702'):
            with self.subTest(origin=invalid), self.assertRaises(ValueError):
                simplify_stroke(straight, 14, native_x_origin=invalid)

    def test_unencodable_native_coordinates_conservatively_keep_every_row(self):
        original = [[20 + i, 1e39, .5, 3.5] for i in range(9)]
        self.assertEqual(simplify_stroke(original, 14), original)

    def test_pressure_width_extrema_and_plateau_boundaries_survive(self):
        levels = [(.2, 2.)] * 10 + [(.9, 3.5)] * 10 + [(.2, 2.)] * 10
        original = [[20 + i * .2, 30., p, w] for i, (p, w) in enumerate(levels)]
        reduced = self.compact(original)
        self.assertTrue({9, 10, 19, 20}.issubset(retained_indices(original, reduced)))
        alternating = [[20 + i * .2, 30., .1 if i % 2 else .9, 2. if i % 2 else 4.]
                       for i in range(129)]
        self.assertEqual(self.compact(alternating), alternating)

    def test_corners_reversals_and_tiny_smooth_loops_remain_marks(self):
        corner = [[20., 30., .5, 3.5], [60., 30., .5, 3.5], [60., 80., .5, 3.5]]
        self.assertEqual(self.compact(corner), corner)
        reverse = [[float(x), 30., .5, 3.5] for x in [20, 30, 40, 50, 40, 30, 20, 40, 60]]
        reduced = self.compact(reverse)
        self.assertIn(3, retained_indices(reverse, reduced))
        self.assertIn(6, retained_indices(reverse, reduced))
        for radius in (1.5, .05):
            loop = [[100 + radius * math.cos(i * math.tau / 128),
                     100 + radius * math.sin(i * math.tau / 128), .5, 3.5] for i in range(129)]
            loop[-1] = list(loop[0])
            reduced = self.compact(loop)
            self.assertGreaterEqual(len(reduced), 4)
            self.assertGreater(area(reduced) * area(loop), 0, 'A closed curved mark became a dot/reversal')

    def test_second_pass_smooth_mixed_dynamics_across_all_tool_profiles(self):
        generator = random.Random(20261104)
        tools = list(BRUSHES)
        for case in range(36):
            tool, width = tools[case % len(tools)], case % 3 + 1
            amplitude, phase = generator.uniform(.05, 3), generator.uniform(0, math.tau)
            samples = [[20 + i * .15, 80 + amplitude * math.sin(i / 27 + phase) + .04 * math.sin(i / 3),
                        .3 + .05 * math.sin(i / 40 + phase)] for i in range(257)]
            with self.subTest(case=case, tool=tool, width=width):
                self.compact(stroke_points(samples, tool, width), tool)

    def test_error_oracle_rejects_lost_extrema_even_with_identical_endpoints(self):
        original = [[20., 30., .2, 2.], [30., 40., .9, 4.], [40., 30., .2, 2.]]
        errors = reconstruction_errors(original, [original[0], original[-1]])
        self.assertGreater(errors['position'], POSITION_ERROR)
        self.assertGreater(errors['pressure'], PRESSURE_ERROR)
        self.assertGreater(errors['encoded_pressure'], PRESSURE_ERROR)
        self.assertGreater(errors['width'], WIDTH_ERROR)

    def test_encoded_pressure_oracle_catches_rounding_hidden_by_raw_pressure_bound(self):
        original = [[20., 30., .49 / 255, 3.5], [30., 30., 1.98 / 255, 3.5],
                    [40., 30., 1.49 / 255, 3.5]]
        errors = reconstruction_errors(original, [original[0], original[-1]])
        self.assertLess(errors['pressure'], PRESSURE_ERROR)
        self.assertGreater(errors['encoded_pressure'], PRESSURE_ERROR)
        self.assertEqual(self.compact(original), original)

    def test_nearest_chord_field_guarantee_rejects_valid_arc_only_counterexample(self):
        fraction = math.hypot(.1, .05) / (math.hypot(.1, .05) + math.hypot(.9, .05))
        original = stroke_points([[20., 30., 0.], [20.1, 30.05, fraction], [21., 30., 1.]], 14, 3)
        arc_only = reconstruction_errors(original, [original[0], original[-1]])
        self.assertLessEqual(arc_only['position'], POSITION_ERROR)
        self.assertLessEqual(arc_only['pressure'], PRESSURE_ERROR)
        self.assertLessEqual(arc_only['encoded_pressure'], PRESSURE_ERROR)
        self.assertLessEqual(arc_only['width'], WIDTH_ERROR)
        self.assertGreater(arc_only['projection_pressure'], PRESSURE_ERROR)
        self.assertEqual(self.compact(original), original)

    def test_point_inspection_work_is_linear_at_capture_limit_and_adversarial_turns(self):
        # Operation counts, not machine-dependent wall-clock timing. A quadratic
        # implementation fails early instead of running a long benchmark.
        for count, zigzag in ((100_000, False), (4096, True)):
            budget = WorkBudget(count * 400)
            original = [CountedPoint([20 + i * .005, 30 + (i % 2 if zigzag else 0), .5, 3.5], budget)
                        for i in range(count)]
            reduced = simplify_stroke(original, 14)
            self.assertLessEqual(budget.reads, count * 400)
            self.assertIs(reduced[0], original[0])
            self.assertIs(reduced[-1], original[-1])
