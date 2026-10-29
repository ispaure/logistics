"""Indexed eraser broad phase must preserve the exact full-scan cut geometry."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import random
import unittest
from unittest.mock import patch

from features.notebooks.eraser import erase
from features.notebooks.ink import Stroke


class EraserIndexTests(unittest.TestCase):
    def test_tangent_contact_does_not_remove_the_entire_segment(self):
        stroke = Stroke('ink', 'visible', 15, 0, [[0, 20, .5, 4], [100, 20, .5, 4]])
        actual = erase([stroke], [('visible', 'Ink', True)], [[50, 10, .5]], 8)
        self.assertEqual(actual, [stroke])
        self.assertIs(actual[0], stroke)

    def test_redundant_path_samples_preserve_cuts_and_reverse_sweeps(self):
        stroke = Stroke('ink', 'visible', 15, 0, [[x, y, .5, 4] for x, y in
            ((0, 20), (100, 20), (100, 80), (0, 80))])
        layers = [('visible', 'Ink', True)]
        paths = ([[50, y, .5] for y in range(101)],
                 [[50, 50, p / 10] for p in range(11)],
                 [[50, 10, .5], [50, 90, .5], [50, 20, .5]],
                 [[20, 10, .5], [50, 50, .5], [70, 20, .5]])
        for path in paths:
            for whole in (False, True):
                with self.subTest(path=path, whole=whole):
                    actual = erase([stroke], layers, path, 8, whole)
                    with patch('features.notebooks.eraser._sweeps',
                               lambda p: list(zip(p, p[1:])) or [(p[0], p[0])]):
                        baseline = erase([stroke], layers, path, 8, whole)
                    self.assertEqual([s.points for s in actual], [s.points for s in baseline])

    def test_dense_paths_wide_sweeps_dots_and_hidden_ink_match_full_scan(self):
        randomizer = random.Random(12345)
        layers = [('visible', 'Ink', True), ('hidden', 'Hidden', False)]
        strokes = [Stroke(str(i), 'hidden' if i == 0 else 'visible', 15, 6,
                          [[randomizer.uniform(0, 1000), randomizer.uniform(0, 1500), .6,
                            randomizer.uniform(.25, 20)] for _ in range(12)]) for i in range(12)]
        strokes += [Stroke('dot', 'visible', 17, 0, [[128, 256, .5, 4]])]
        paths = [[[i * 4, 256 + randomizer.uniform(-20, 20), .5] for i in range(200)],
                 [[0, 0, .5], [1000, 1500, .5]] * 20,
                 [[128, 256, .5]] * 40]
        for path in paths:
            for whole in (False, True):
                for radius in (8, 16, 32):
                    with self.subTest(whole=whole, radius=radius):
                        indexed = erase(strokes, layers, path, radius, whole)
                        with patch('features.notebooks.eraser._INDEX_THRESHOLD', float('inf')):
                            baseline = erase(strokes, layers, path, radius, whole)
                        def geometry(items):
                            return [(s.layer, s.tool, s.color, s.scale, s.color_rgba, s.points) for s in items]
                        self.assertEqual(geometry(indexed), geometry(baseline))
                        self.assertIs(indexed[0], strokes[0])
