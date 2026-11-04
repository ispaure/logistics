"""Actual editor/save/export/recovery acceptance for new-stroke compaction."""
from copy import deepcopy
from dataclasses import asdict
from io import BytesIO
import json
import math
import struct
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from commonUtils.testing.stages import TestStage
from features.notebooks._vendor.rmscene import scene_items as si, scene_stream as ss
from features.notebooks.brushes import BRUSHES, native_color, native_scale, stroke_points
from features.notebooks.editor import Editor
from features.notebooks.ink import InkPage, WIDTH, encode
from features.notebooks.notebook import Notebook
from features.notebooks.protocol import stroke_script
from features.notebooks.recovery import Repository
from features.notebooks.remarkable_export import export_rmdoc
from tests.notebooks.test_sampling_native_preservation import imported_book, native_line

TEST_STAGE = TestStage.REGRESSION


def scene_from_archive(data, book):
    with ZipFile(BytesIO(data)) as archive:
        return archive.read(f'{book.id}/{book.pages[0].id}.rm')


def full_stream_control(actual_scene, computed):
    """Use the real codec and identical metadata with every pre-compaction row.

    This is the old writer's native representation, not a fake renderer/backend
    or a monkeypatch of the production sampler or serializer.
    """
    blocks = list(ss.read_blocks(BytesIO(actual_scene)))
    line = next(block.item.value for block in blocks if isinstance(block, ss.SceneLineItemBlock))
    line.points = [si.Point(x - WIDTH / 2, y, 0, 0, round(width * 4), round(pressure * 255))
                   for x, y, pressure, width in computed]
    return encode(blocks)


class SamplingWorkflowTests(unittest.TestCase):
    def assert_metadata(self, stroke, tool, color, width, layer):
        native, rgba = native_color(tool, color)
        self.assertEqual((stroke.tool, stroke.color, stroke.color_rgba, stroke.layer, stroke.scale),
                         (tool, native, rgba, layer, native_scale(tool, width)))

    def test_actual_editor_action_save_export_undo_redo_and_recovery_all_brushes(self):
        for tool in BRUSHES:
            with self.subTest(tool=tool), TemporaryDirectory() as directory:
                book = Notebook.new('Synthetic saved compaction workflow')
                book.page(0).add_layer('Sampling QA')
                repository = Repository(directory)
                key = repository.create(book)
                layer = book.page(0).layers[-1][0]
                editor = Editor(book, lambda value: repository.save(key, value))
                samples = [[20 + i * .05, 80., .6] for i in range(1000)]
                untouched = deepcopy(samples)
                color, width = 6, 2
                computed = stroke_points(samples, tool, width)
                editor.apply(dict(op='stroke', points=samples, tool=tool, color=color,
                                  width=width, layer=layer))
                self.assertEqual(samples, untouched)
                stroke = book.page(0).strokes[0]
                expected_count = 1000 if tool == 21 else 2
                self.assertEqual(len(stroke.points), expected_count)
                self.assert_metadata(stroke, tool, color, width, layer)
                message = stroke_script(editor, None)
                self.assertTrue(message.startswith('window.notebookStrokeUpdate('))
                acknowledged, _ = json.JSONDecoder().raw_decode(message[len('window.notebookStrokeUpdate('):])
                self.assertEqual(acknowledged['points'], stroke.points)
                self.assertEqual(len(acknowledged['points']), expected_count)

                actual = book.page(0).to_bytes()
                control = full_stream_control(actual, computed)
                actual_native, original_native = native_line(actual), native_line(control)
                self.assertEqual(len(actual_native.points), expected_count)
                self.assertEqual(len(original_native.points), len(samples))
                expected_native = original_native.points if tool == 21 else [original_native.points[0], original_native.points[-1]]
                self.assertEqual([asdict(point) for point in actual_native.points],
                                 [asdict(point) for point in expected_native])
                if tool != 21:
                    # Fourteen bytes per native point, plus a small point-count
                    # length encoding difference. This is actual scene size.
                    self.assertGreaterEqual(len(control) - len(actual), 14 * (len(samples) - expected_count))

                reopened = Notebook.read(book.to_bytes())
                self.assertEqual(reopened.page(0).strokes[0].points, stroke.points)
                self.assert_metadata(reopened.page(0).strokes[0], tool, color, width, layer)
                metadata, content = deepcopy(book.metadata), deepcopy(book.content)
                exported = export_rmdoc(book)
                self.assertEqual(scene_from_archive(exported, book), actual)
                self.assertEqual((book.metadata, book.content), (metadata, content))
                portable = Notebook.read(exported).page(0).strokes[0]
                self.assertEqual(portable.points, stroke.points)
                self.assert_metadata(portable, tool, color, width, layer)

                editor.apply(dict(op='undo'))
                self.assertEqual(book.page(0).strokes, [])
                editor.apply(dict(op='redo'))
                self.assertEqual(book.page(0).to_bytes(), actual)
                recovered = repository.open(key).page(0).strokes[0]
                self.assertEqual(recovered.points, stroke.points)
                self.assert_metadata(recovered, tool, color, width, layer)

    def test_mixed_imported_native_metadata_and_new_reduced_stroke(self):
        book, raw = imported_book()
        imported = [asdict(point) for point in native_line(raw).points]
        editor = Editor(book)
        samples = [[80 + i * .05, 120., .6] for i in range(1000)]
        editor.apply(dict(op='stroke', points=samples, tool=17, color=7, width=2))
        self.assertEqual(len(book.page(0).strokes[0].points), 129)
        self.assertEqual(len(book.page(0).strokes[1].points), 2)
        written = book.page(0).to_bytes()
        self.assertTrue(written.startswith(raw))
        self.assertEqual([asdict(point) for point in native_line(written).points], imported)
        self.assertEqual(scene_from_archive(export_rmdoc(book), book), written)

    def test_nonadvancing_numeric_arc_fallback_reaches_actual_editor_save_path(self):
        samples = [[0., 0., .5], [1., 0., .5], [2., 0., .5]]
        samples.extend([[1404. if index % 2 == 0 else 0., 0., .5] for index in range(256)])
        distance = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(samples, samples[1:]))
        step = 1e-12
        self.assertEqual(distance + step, distance)
        samples.extend([[step, 0., .51], [step * 2, 0., .8], [step * 3, 0., .9]])
        untouched = deepcopy(samples)
        book = Notebook.new('Synthetic numerical fallback')
        Editor(book).apply(dict(op='stroke', points=samples, tool=17, color=0, width=2))
        self.assertEqual(samples, untouched)
        self.assertEqual(book.page(0).strokes[0].points, stroke_points(samples, 17, 2))
        self.assertEqual(len(native_line(book.page(0).to_bytes()).points), len(samples))

    def test_native_float32_coincident_pressure_ramp_reaches_editor_and_archive(self):
        samples = [[x, 10., p] for x, p in zip((1e-5, 2e-5, 3e-5), (.2, .5, .8))]
        self.assertEqual(len({struct.pack('<f', point[0] - WIDTH / 2) for point in samples}), 1)
        book = Notebook.new('Synthetic encoded stationary pressure')
        Editor(book).apply(dict(op='stroke', points=samples, tool=17, color=0, width=2))
        self.assertEqual(len(book.page(0).strokes[0].points), 3)
        points = native_line(book.page(0).to_bytes()).points
        self.assertEqual(len(points), 3)
        self.assertEqual(len({(point.x, point.y) for point in points}), 1)
        self.assertEqual([point.pressure for point in points], [round(p[2] * 255) for p in samples])

    def test_large_page_float32_precision_keeps_encoded_stationary_dynamics(self):
        samples = [[20., 999999 + step, p] for step, p in zip((.001, .002, .003), (.2, .5, .8))]
        self.assertEqual(len({struct.pack('<f', point[1]) for point in samples}), 1)
        page = InkPage.blank()
        page.add(samples, tool=17, color=0, width=2, page_height=1_000_000)
        self.assertEqual(len(page.strokes[0].points), 3)
        encoded = native_line(page.to_bytes()).points
        self.assertEqual(len(encoded), 3)
        self.assertEqual(len({point.y for point in encoded}), 1)
        self.assertEqual([point.pressure for point in encoded], [round(p[2] * 255) for p in samples])
