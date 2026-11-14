"""Receipt checks for synthetic PDF-backed notebook stroke calibration."""
import json
import unittest
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from features.notebooks.editor import Editor
from tests.notebooks.corpus_calibration import calibrate

TEST_STAGE = TestStage.REGRESSION


class CorpusCalibrationTests(unittest.TestCase):
    def test_width_receipt_covers_pdf_geometry_and_portable_roundtrips(self):
        report = calibrate()
        self.assertTrue(report['passed'])
        self.assertEqual(json.loads(json.dumps(report, allow_nan=False)), report)
        cases = {(case['layout'], case['fixture']): case for case in report['cases']}
        self.assertEqual(len(cases), 15)

        def bounds(fixture):
            return cases['modern', fixture]['geometry']['model']['paper_bounds']

        portrait = bounds('portrait-300x600')
        rotated = bounds('rotated-90')
        crop = bounds('offset-crop')
        self.assertEqual(bounds('user-unit-2'), portrait)
        self.assertAlmostEqual(rotated['width'], portrait['height'])
        self.assertAlmostEqual(rotated['height'], portrait['width'])
        self.assertAlmostEqual(crop['width'], portrait['width'] * .8)
        self.assertAlmostEqual(crop['height'], portrait['height'] * .8)
        legacy = cases['legacy', 'large-954x1696']
        self.assertIsNone(legacy['geometry']['model']['paper_bounds'])
        self.assertEqual(legacy['normalization_height'], 1872)
        modern = cases['modern', 'large-954x1696']
        self.assertAlmostEqual(modern['geometry']['model']['canvas_left'], -795.25)
        self.assertTrue(all(modern['archive'].values()))
        strokes = {row['tool']: row for row in modern['strokes']}
        self.assertEqual(strokes['Imported Highlighter']['width_ratio_to_plain'], [1, 1])
        self.assertEqual(strokes['Fineliner medium']['observed']['saved'], [12.5, 12.5])
        self.assertEqual(strokes['Highlighter fixed']['observed']['exported'], [94.25, 94.25])
        self.assertAlmostEqual(strokes['Highlighter fixed']['height_normalized_ratio_to_plain'][0], 1.2747119719)

    def test_receipt_detects_double_application_of_imported_thickness(self):
        original = Editor.canvas_stroke

        def twice(editor, stroke):
            payload = original(editor, stroke)
            if stroke.scale == 2.625 and editor.expanded_ink():
                payload['points'] = [[x, y, pressure, width * stroke.scale]
                                     for x, y, pressure, width in payload['points']]
            return payload

        with patch.object(Editor, 'canvas_stroke', twice):
            report = calibrate()
        self.assertFalse(report['passed'])
        self.assertTrue(report['cases'][0]['passed'])
        self.assertFalse(report['cases'][-1]['passed'])
        imported = report['cases'][-1]['strokes'][0]
        self.assertGreater(imported['max_abs_error'], 0)
        self.assertEqual(imported['expected'], imported['observed']['exported'])
