"""New-stroke compaction must never rewrite dense imported native ink."""
from dataclasses import asdict
from io import BytesIO
from tempfile import TemporaryDirectory
import unittest

from commonUtils.testing.stages import TestStage
from features.notebooks._vendor.rmscene import scene_items as si, scene_stream as ss
from features.notebooks.editor import Editor
from features.notebooks.ink import InkPage, WIDTH, encode
from features.notebooks.notebook import Notebook
from features.notebooks.recovery import Repository

TEST_STAGE = TestStage.REGRESSION


def native_line(raw):
    return next(block.item.value for block in ss.read_blocks(BytesIO(raw))
                if isinstance(block, ss.SceneLineItemBlock) and block.item.value is not None)


def imported_book():
    book = Notebook.new('Synthetic dense imported native ink')
    page = InkPage.blank()
    page.add([[20., 40., .5], [52., 40., .5]], tool=14, width=2)
    blocks = list(ss.read_blocks(BytesIO(page.to_bytes())))
    line = next(block.item.value for block in blocks if isinstance(block, ss.SceneLineItemBlock))
    # Native metadata is deliberately meaningful although geometry is redundant.
    # A global resampling pass would lose both point count and these fields.
    line.points = [si.Point(20 + i * .25 - WIDTH / 2, 40., i * 83, i % 256, 14, 128)
                   for i in range(129)]
    raw = encode(blocks)
    book.members[f'{book.id}/{book.pages[0].id}.rm'] = raw
    book.pages[0].ink = InkPage.read(raw)
    return book, raw


class SamplingNativePreservationTests(unittest.TestCase):
    def test_read_and_unchanged_save_keep_every_native_frame_byte(self):
        book, raw = imported_book()
        self.assertEqual(book.page(0).to_bytes(), raw)
        reopened = Notebook.read(book.to_bytes())
        self.assertEqual(reopened.page(0).to_bytes(), raw)
        self.assertEqual(len(reopened.page(0).strokes[0].points), 129)

    def test_unsupported_future_native_color_is_preserved_and_not_sampled(self):
        _, raw = imported_book()
        blocks = list(ss.read_blocks(BytesIO(raw)))
        line = next(block.item.value for block in blocks if isinstance(block, ss.SceneLineItemBlock))
        line.color = 99
        future_raw = encode(blocks)
        page = InkPage.read(future_raw)
        self.assertTrue(page.warning)
        with self.assertRaises(ValueError):
            page.add([[20., 30., .5], [40., 30., .5]], tool=14, width=2)
        self.assertEqual(page.to_bytes(), future_raw)

    def test_adding_new_ink_keeps_imported_point_count_and_hidden_native_fields(self):
        book, raw = imported_book()
        expected = [asdict(point) for point in native_line(raw).points]
        book.page(0).add([[80 + i * .1, 80., .5] for i in range(257)], tool=17, width=2)
        written = book.page(0).to_bytes()
        self.assertTrue(written.startswith(raw), 'An unrelated new stroke rewrote imported frames')
        self.assertEqual([asdict(point) for point in native_line(written).points], expected)
        self.assertEqual(len(book.page(0).strokes[0].points), 129)

    def test_translation_keeps_imported_sampling_and_nonpositional_native_fields(self):
        book, raw = imported_book()
        before = native_line(raw).points
        identity = book.page(0).strokes[0].id
        Editor(book).apply(dict(op='transform', ids=[identity], dx=13., dy=17.))
        after = native_line(book.page(0).to_bytes()).points
        self.assertEqual(len(after), len(before))
        for original, moved in zip(before, after):
            self.assertEqual((moved.x, moved.y), (original.x + 13, original.y + 17))
            self.assertEqual((moved.speed, moved.direction, moved.width, moved.pressure),
                             (original.speed, original.direction, original.width, original.pressure))

    def test_partial_eraser_does_not_resample_surviving_imported_points(self):
        book, raw = imported_book()
        original = book.page(0).strokes[0].points
        preserved = {tuple(point) for point in original if point[0] <= 25 or point[0] >= 47}
        editor = Editor(book)
        editor.apply(dict(op='erase', points=[[36., 10., .5], [36., 70., .5]], radius=8, kind='partial'))
        fragments = book.page(0).strokes
        self.assertEqual(len(fragments), 2)
        self.assertTrue(preserved.issubset({tuple(point) for stroke in fragments for point in stroke.points}))
        editor.apply(dict(op='undo'))
        self.assertEqual(book.page(0).to_bytes(), raw)
        editor.apply(dict(op='redo'))
        self.assertEqual(len(book.page(0).strokes), 2)

    def test_recovery_does_not_compact_dense_imported_native_frames(self):
        book, raw = imported_book()
        with TemporaryDirectory() as directory:
            repository = Repository(directory)
            key = repository.create(book)
            repository.save(key, book)
            reopened = repository.open(key)
            self.assertEqual(reopened.page(0).to_bytes(), raw)
            self.assertEqual(len(reopened.page(0).strokes[0].points), 129)
