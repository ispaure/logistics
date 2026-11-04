"""On-screen graphite never participates in native ink or background export."""
from io import BytesIO
from dataclasses import asdict
import unittest
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from features.notebooks.notebook import Notebook
from features.notebooks.remarkable_export import export_rmdoc
from tests.notebooks.graphite_fixtures import archive_members, graphite_notebook, snapshot_export

TEST_STAGE = TestStage.REGRESSION


class GraphiteExportBoundaryTests(unittest.TestCase):
    def test_portable_export_preserves_graphite_scene_bytes_without_canvas(self):
        from pypdf import PdfReader
        book = graphite_notebook()
        original = archive_members(book.to_bytes())
        with patch('features.notebooks.canvas.asset', side_effect=AssertionError('Canvas is display-only')):
            exported = archive_members(export_rmdoc(book))
        scenes = {name: data for name, data in original.items() if name.endswith('.rm')}
        self.assertTrue(scenes)
        self.assertEqual(scenes, {name: exported[name] for name in scenes})
        self.assertEqual(archive_members(book.to_bytes()), original)
        pdf = PdfReader(BytesIO(exported[book.id + '.pdf']))
        self.assertTrue(pdf.pages)
        for page in pdf.pages:
            self.assertFalse(page.get('/Resources', {}).get('/XObject'))

    def test_native_roundtrip_keeps_pencil_geometry_and_preset_fields(self):
        book = graphite_notebook()
        signature = [asdict(stroke) for stroke in book.page(0).strokes]
        reopened = Notebook.read(book.to_bytes())
        self.assertEqual([asdict(stroke) for stroke in reopened.page(0).strokes], signature)
        self.assertEqual([stroke.tool for stroke in reopened.page(0).strokes], [14, 13])

    def test_render_export_comparison_pins_only_export_clock_input(self):
        book = graphite_notebook()
        with patch('features.notebooks.notebook.time.time', return_value=1_700_000_000):
            earlier = archive_members(export_rmdoc(book))
            fixed_earlier = archive_members(snapshot_export(book))
        with patch('features.notebooks.notebook.time.time', return_value=1_700_000_030):
            later = archive_members(export_rmdoc(book))
            fixed_later = archive_members(snapshot_export(book))
        self.assertNotEqual(earlier, later)
        self.assertEqual(fixed_earlier, fixed_later)
        self.assertEqual(fixed_earlier, earlier)
