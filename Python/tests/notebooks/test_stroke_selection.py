"""Native editing behavior behind the shared desktop/mobile lasso controls."""
from copy import deepcopy
import math
from tempfile import TemporaryDirectory
import unittest

from commonUtils.testing.stages import TestStage
from features.notebooks.editor import Editor
from features.notebooks.notebook import Notebook
from features.notebooks.protocol import validate_action
from features.notebooks.recovery import Repository
from tests.notebooks.test_sampling_native_preservation import imported_book, native_line

TEST_STAGE = TestStage.REGRESSION


class StrokeSelectionTests(unittest.TestCase):
    def editor(self, checkpoint=lambda book: None):
        book = Notebook.new('Selection')
        editor = Editor(book, checkpoint)
        editor.apply(dict(op='stroke', points=[[100, 100, .4], [120, 100, .8]], tool=17, color=6, width=2))
        return editor

    def transform(self, editor, **changes):
        action = dict(op='transform', ids=[s.id for s in editor.notebook.page(editor.index).strokes], dx=0, dy=0)
        editor.apply(action | changes)

    def test_uniform_scale_rotation_keeps_pressure_color_and_width(self):
        editor = self.editor()
        original = deepcopy(editor.notebook.page(0).strokes[0])
        self.transform(editor, scale=2, angle=math.pi/2, cx=100, cy=100)
        stroke = editor.notebook.page(0).strokes[0]
        self.assertAlmostEqual(stroke.points[-1][0], 100)
        self.assertAlmostEqual(stroke.points[-1][1], 140)
        self.assertEqual(stroke.points[-1][2], original.points[-1][2])
        self.assertEqual(stroke.points[-1][3], original.points[-1][3]*2)
        self.assertEqual(stroke.scale, original.scale*2)
        self.assertEqual(stroke.color_rgba, original.color_rgba)
        editor.apply(dict(op='undo'))
        self.assertEqual(editor.notebook.page(0).strokes[0].payload(), original.payload())
        editor.apply(dict(op='redo'))
        self.assertAlmostEqual(editor.notebook.page(0).strokes[0].points[-1][1], 140)

    def test_failed_transform_is_atomic_and_preserves_history(self):
        editor = self.editor()
        editor.apply(dict(op='stroke', points=[[1300, 100, .5]], width=2))
        before = [s.payload() for s in editor.notebook.page(0).strokes]
        count = len(editor.undo)
        with self.assertRaises(ValueError):
            self.transform(editor, dx=200)
        self.assertEqual([s.payload() for s in editor.notebook.page(0).strokes], before)
        self.assertEqual(len(editor.undo), count)

    def test_copy_is_not_an_edit_cross_page_paste_keeps_position_and_fresh_ids(self):
        editor = self.editor()
        original = deepcopy(editor.notebook.page(0).strokes[0])
        history = len(editor.undo)
        editor.apply(dict(op='copy-strokes', ids=[original.id]))
        self.assertEqual(len(editor.undo), history)
        editor.apply(dict(op='add-page'))
        for _ in range(2):
            editor.apply(dict(op='paste-strokes'))
        copies = editor.notebook.page(1).strokes
        self.assertEqual(len(copies), 2)
        self.assertEqual(copies[0].points, original.points)
        self.assertEqual(copies[1].points, original.points)
        self.assertEqual(len({original.id, copies[0].id, copies[1].id}), 3)
        self.assertTrue(editor.state()['stroke_clipboard'])
        self.assertEqual(editor.state()['selection_ids'], [copies[-1].id])
        self.assertEqual(editor.notebook.page(1).order, [s.id for s in copies])

    def test_cut_undo_redo_and_paste_keep_clipboard(self):
        editor = self.editor()
        original = deepcopy(editor.notebook.page(0).strokes[0])
        editor.apply(dict(op='cut-strokes', ids=[original.id]))
        self.assertFalse(editor.notebook.page(0).strokes)
        editor.apply(dict(op='undo'))
        self.assertEqual(editor.notebook.page(0).strokes[0].points, original.points)
        editor.apply(dict(op='redo'))
        self.assertFalse(editor.notebook.page(0).strokes)
        editor.apply(dict(op='paste-strokes'))
        self.assertEqual(editor.notebook.page(0).strokes[0].points, original.points)

    def test_failed_checkpoint_rolls_back_cut_and_clipboard(self):
        editor = self.editor()
        original = editor.notebook.page(0).strokes[0]
        def fail(book):
            raise ValueError('read-only checkpoint')
        editor.checkpoint = fail
        with self.assertRaisesRegex(ValueError, 'read-only'):
            editor.apply(dict(op='cut-strokes', ids=[original.id]))
        self.assertEqual(editor.notebook.page(0).strokes, [original])
        self.assertFalse(editor.state()['stroke_clipboard'])

    def test_hidden_and_missing_strokes_cannot_be_manipulated(self):
        editor = self.editor()
        stroke = editor.notebook.page(0).strokes[0]
        ink = editor.notebook.page(0)
        ink.layers = [(key, name, False) for key, name, _ in ink.layers]
        for op in ('copy-strokes', 'cut-strokes', 'transform'):
            with self.subTest(op=op), self.assertRaises(ValueError):
                editor.apply(dict(op=op, ids=[stroke.id], dx=0, dy=0))
        with self.assertRaises(ValueError):
            editor.apply(dict(op='copy-strokes', ids=['missing']))

    def test_native_transform_preserves_dynamics_and_encodes_scale(self):
        book, *_ = imported_book()
        editor = Editor(book)
        ink = book.page(0)
        before = native_line(ink.to_bytes())
        ids = [ink.strokes[0].id]
        editor.apply(dict(op='transform', ids=ids, dx=0, dy=0, scale=1.1, cx=200, cy=200, angle=.02))
        line = native_line(book.page(0).to_bytes())
        self.assertEqual([(p.speed,p.direction,p.pressure) for p in line.points],
                         [(p.speed,p.direction,p.pressure) for p in before.points])
        self.assertAlmostEqual(line.thickness_scale, before.thickness_scale*1.1)
        self.assertEqual([p.width for p in line.points], [round(p.width*1.1) for p in before.points])

    def test_noop_keeps_native_scene_identical(self):
        book, *_ = imported_book()
        editor = Editor(book)
        before = book.page(0).to_bytes()
        self.transform(editor)
        self.assertEqual(book.page(0).to_bytes(), before)

    def test_recovery_normalization_returns_new_native_selection_ids(self):
        with TemporaryDirectory() as directory:
            repository = Repository(directory)
            book = Notebook.new('Selection recovery')
            key = repository.create(book)
            editor = Editor(book, lambda value: repository.save(key, value))
            editor.apply(dict(op='stroke', points=[[100,100,.5], [110,110,.5]], width=2))
            editor.apply(dict(op='copy-strokes', ids=[book.page(0).strokes[0].id]))
            editor.apply(dict(op='paste-strokes'))
            self.assertEqual(editor.state()['selection_ids'], [book.page(0).strokes[-1].id])
            self.assertIn(':', editor.state()['selection_ids'][0])
            editor.apply(dict(op='undo'))
            self.assertEqual(len(book.page(0).strokes), 1)
            editor.apply(dict(op='redo'))
            self.assertEqual(len(book.page(0).strokes), 2)

    def test_transform_shape_validation_rejects_nonfinite_boolean_and_scale_limits(self):
        for changes in ({'scale':0}, {'scale':21}, {'scale':True}, {'angle':float('nan')},
                        {'cx':float('inf')}, {'dy':False}, {'ids':[1]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_action(dict(op='transform', ids=['a'], dx=0, dy=0) | changes)

    def test_mobile_single_use_paste_consumes_only_confirmed_clipboard_and_copy_rearms(self):
        editor = self.editor()
        original = editor.notebook.page(0).strokes[0]
        editor.apply(dict(op='copy-strokes', ids=[original.id]))
        editor.apply(dict(op='paste-strokes', single_use=True))
        self.assertEqual(len(editor.notebook.page(0).strokes), 2)
        self.assertFalse(editor.state()['stroke_clipboard'])
        with self.assertRaises(ValueError):
            editor.apply(dict(op='paste-strokes', single_use=True))
        self.assertEqual(len(editor.notebook.page(0).strokes), 2)
        editor.apply(dict(op='copy-strokes', ids=[editor.notebook.page(0).strokes[0].id]))
        self.assertTrue(editor.state()['stroke_clipboard'])
        editor.apply(dict(op='paste-strokes', single_use=True))
        self.assertEqual(len(editor.notebook.page(0).strokes), 3)
        self.assertFalse(editor.state()['stroke_clipboard'])

    def test_mobile_failed_paste_keeps_clipboard_for_retry_until_checkpoint_succeeds(self):
        editor = self.editor()
        editor.apply(dict(op='copy-strokes', ids=[editor.notebook.page(0).strokes[0].id]))
        before = [stroke.payload() for stroke in editor.notebook.page(0).strokes]
        def fail(book):
            raise OSError('synthetic checkpoint failure')
        editor.checkpoint = fail
        with self.assertRaisesRegex(OSError, 'checkpoint failure'):
            editor.apply(dict(op='paste-strokes', single_use=True))
        self.assertEqual([stroke.payload() for stroke in editor.notebook.page(0).strokes], before)
        self.assertTrue(editor.state()['stroke_clipboard'])
        editor.checkpoint = lambda book: None
        editor.apply(dict(op='paste-strokes', single_use=True))
        self.assertEqual(len(editor.notebook.page(0).strokes), 2)
        self.assertFalse(editor.state()['stroke_clipboard'])

    def test_single_use_paste_flag_rejects_nonboolean_values(self):
        for value in ('true', 1, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_action(dict(op='paste-strokes', single_use=value))
