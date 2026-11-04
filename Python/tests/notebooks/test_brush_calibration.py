"""Synthetic checks against aggregate Paper Pro OS 3.29.0.153 measurements.

No handwriting, raw user archive, original coordinates or identifying notes are
fixtures. Imported examples below are independently constructed scene lines.
"""
from io import BytesIO
import unittest

from commonUtils.testing.stages import TestStage
from features.notebooks._vendor.rmscene import scene_stream as ss
from features.notebooks.brushes import (
    NATIVE_SCALES, NATIVE_HIGHLIGHTS, PALETTE, native_color, stroke_points,
)
from features.notebooks.ink import InkPage, encode

TEST_STAGE = TestStage.REGRESSION


class BrushCalibrationTests(unittest.TestCase):
    def test_constant_native_widths_and_highlighter_single_size(self):
        samples = [[20, 30, .01], [40, 30, .5], [60, 30, 1]]
        for tool, widths in [(17, (2, 3.5, 5.25)), (13, (3.5, 5.25, 7.75)),
                             (18, (26, 26, 26))]:
            for width, expected in enumerate(widths, 1):
                self.assertEqual([p[3] for p in stroke_points(samples, tool, width)], [expected] * 3)

    def test_shader_pressure_saturates_without_growing_after_point_three(self):
        samples = [[20, 30, 0], [40, 30, .3], [60, 30, .8], [80, 30, 1]]
        for width, low, high in [(1, 3.5, 10.75), (2, 6.5, 19.5), (3, 9.25, 28)]:
            self.assertEqual([p[3] for p in stroke_points(samples, 23, width)], [low, high, high, high])

    def test_measured_thickness_scales_are_written_once(self):
        for width, expected in enumerate(NATIVE_SCALES, 1):
            page = InkPage.blank()
            page.add([[20, 30, .5], [40, 30, 1]], tool=17, width=width)
            decoded = InkPage.read(page.to_bytes())
            self.assertFalse(decoded.warning)
            self.assertEqual(decoded.strokes[0].scale, expected)
            self.assertEqual(decoded.strokes[0].points[0][3], (2, 3.5, 5.25)[width - 1])
            page = InkPage.blank()
            page.add([[20, 30, .5]], tool=18, color=13, width=width)
            self.assertEqual(InkPage.read(page.to_bytes()).strokes[0].scale, NATIVE_SCALES[0])

    def test_measured_highlighter_ids_open_and_preserve_raw_frames(self):
        for choice, expected in [(13, 3), (10, 4), (5, 5), (6, 14), (-1, 15), (1, 16)]:
            self.assertEqual(native_color(18, choice), (expected, None))
            page = InkPage.blank()
            page.add([[20, 30, .5], [40, 30, .8]], tool=18, color=choice)
            raw = page.to_bytes()
            decoded = InkPage.read(raw)
            self.assertFalse(decoded.warning)
            self.assertEqual(decoded.strokes[0].color, expected)
            self.assertEqual(decoded.to_bytes(), raw)
            self.assertEqual(NATIVE_HIGHLIGHTS[expected][3], 255)

    def test_legacy_rgba_highlights_and_unknown_future_colors_keep_preservation(self):
        page = InkPage.blank()
        page.add([[20, 30, .5]], tool=18, color=13)
        blocks = list(ss.read_blocks(BytesIO(page.to_bytes())))
        line = next(b.item.value for b in blocks if isinstance(b, ss.SceneLineItemBlock))
        line.color, line.color_rgba = 9, (12, 34, 56, 117)
        raw = encode(blocks)
        decoded = InkPage.read(raw)
        self.assertFalse(decoded.warning)
        self.assertEqual(decoded.strokes[0].color_rgba, (12, 34, 56, 117))
        self.assertEqual(decoded.to_bytes(), raw)
        line.color = 99
        unknown = encode(blocks)
        decoded = InkPage.read(unknown)
        self.assertTrue(decoded.warning)
        self.assertEqual(decoded.to_bytes(), unknown)

    def test_native_writing_palette_from_exported_pdf(self):
        self.assertEqual({key: PALETTE[key] for key in (6, 7, 10, 13, 11, 12)},
                         {6: '#304ae0', 7: '#c23132', 10: '#91da71',
                          13: '#fae719', 11: '#74d2e8', 12: '#c07fd2'})
