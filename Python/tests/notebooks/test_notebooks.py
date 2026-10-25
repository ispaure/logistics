"""Synthetic native-ink archives, recovery, preservation and editing contracts."""
import json
from io import BytesIO
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import quote
from zipfile import ZipFile

from features.notebooks._vendor.rmscene import scene_stream as ss
from features.notebooks._vendor.rmscene.tagged_block_common import HEADER_V6
from features.notebooks._vendor.rmscene.scene_tree import SceneTree
from features.notebooks.notebook import Notebook, read_archive
from features.notebooks.ink import InkPage, TOOLS, COLORS
from features.notebooks.workspace import Repository, Editor
from features.notebooks.bridge import Bridge


def archive(members):
    out = BytesIO()
    with ZipFile(out, 'w') as z:
        for key, value in members.items():
            z.writestr(key, value)
    return out.getvalue()


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Repository(self.directory.name)
        self.book = Notebook.new('Synthetic notebook')
        self.key = self.repo.create(self.book)
        self.editor = Editor(self.book, lambda b: self.repo.save(self.key, b))

    def draw(self, tool=17, color=0):
        self.editor.apply(dict(op='stroke', points=[[10,20,.25],[50,60,.8]],tool=tool,color=color))

    def test_layers_visibility_and_recovery_conflict(self):
        self.draw()
        self.editor.apply(dict(op='add-layer',name='Second layer'))
        ink = self.book.page(0)
        second = ink.layers[-1][0]
        self.assertEqual(len(ink.layers),2)
        self.editor.apply(dict(op='stroke',points=[[20,30,.5]],layer=second))
        self.editor.apply(dict(op='layer-visible',layer=second,visible=False))
        restored = self.repo.open(self.key)
        self.assertFalse(restored.page(0).layers[-1][2])
        self.assertEqual(len(restored.page(0).strokes),2)
        stale = self.repo.open(self.key)
        self.draw()
        with self.assertRaisesRegex(ValueError,'another window'):
            self.repo.save(self.key,stale)

    def test_long_cpages_order_keys_are_unique_sorted_and_bounded(self):
        from features.notebooks.notebook import page_order_key
        keys = [page_order_key(i) for i in range(1000)]
        self.assertEqual(keys[:2],['ba','bb'])
        self.assertEqual(keys[25:28],['bz','caa','cab'])
        self.assertEqual(keys, sorted(set(keys)))
        self.assertLess(max(map(len,keys)),6)

    def test_native_scene_geometry_brush_pressure_and_independent_wire_fields(self):
        self.draw()
        data = self.book.to_bytes()
        members = read_archive(data)
        ink = members[f'{self.book.id}/{self.book.pages[0].id}.rm']
        tree = SceneTree()
        ss.build_tree(tree, ss.read_blocks(BytesIO(ink)))
        line = list(tree.walk())[0]
        self.assertAlmostEqual(line.points[0].x, -692)
        self.assertEqual(line.points[1].pressure, 204)
        self.assertEqual(int(line.tool), 17)
        # Independent wire inspection: locate the native float coordinate pair
        # and fixed point fields, without the application's decoder.
        point = struct.pack('<ffHHBB', -692.,20.,0,8,0,64)
        self.assertIn(point, ink)
        self.assertTrue(ink.startswith(HEADER_V6))

    def test_all_declared_brushes_and_colors_encode_as_native_ink(self):
        for tool in TOOLS.values():
            for color in COLORS.values():
                self.book.page(0).add([[10,20,.25],[30,40,.9]],tool,color)
        ink = InkPage.read(self.book.page(0).to_bytes())
        self.assertFalse(ink.warning)
        self.assertEqual(len(ink.strokes), len(TOOLS)*len(COLORS))

    def test_save_reopen_erase_undo_redo_transform(self):
        self.draw()
        identity = self.book.page(0).strokes[0].id
        self.editor.apply(dict(op='transform',ids=[identity],dx=12,dy=3))
        self.assertEqual(self.repo.open(self.key).page(0).strokes[0].points[0][:2],[22,23])
        self.editor.apply(dict(op='erase',ids=[identity]))
        self.assertFalse(self.repo.open(self.key).page(0).strokes)
        self.editor.apply(dict(op='undo'))
        self.assertEqual(len(self.repo.open(self.key).page(0).strokes),1)
        self.editor.apply(dict(op='redo'))
        self.assertFalse(self.book.page(0).strokes)

    def test_add_duplicate_reorder_delete_and_copy_opaque_sidecar(self):
        self.draw()
        page = self.book.pages[0]
        self.book.members[f'{self.book.id}/{page.id}-metadata.json'] = b'not-a-owned-extension'
        self.book.members[f'{self.book.id}/{page.id}.metadata'] = b'{"unknown": 5}'
        target = Notebook.new('Target')
        target.copy_page(self.book,0)
        self.assertEqual(len(target.pages),2)
        new_id = target.pages[1].id
        self.assertNotEqual(new_id,page.id)
        result = Notebook.read(target.to_bytes())
        self.assertEqual(len(result.page(1).strokes),1)
        self.assertEqual(result.members[f'{target.id}/{new_id}.metadata'],b'{"unknown": 5}')
        self.editor.apply(dict(op='duplicate-page'))
        self.editor.apply(dict(op='move-page',index=0))
        self.editor.apply(dict(op='delete-page'))
        self.assertEqual(len(self.repo.open(self.key).pages),1)

    def test_unmodified_unknown_members_and_scene_frames_are_exact(self):
        self.draw()
        data = self.book.to_bytes()
        members = read_archive(data)
        members['opaque/future.bin'] = b'\x01\xffunrecognized'
        imported = Notebook.read(archive(members))
        before = imported.page(0).raw
        imported.page(0).add([[100,100,.5],[120,120,.5]])
        after = imported.page(0).to_bytes()
        self.assertTrue(after.startswith(before))
        result = read_archive(imported.to_bytes())
        self.assertEqual(result['opaque/future.bin'],members['opaque/future.bin'])
        for name, value in members.items():
            if name.endswith('.rm') or name.endswith('.metadata'):
                continue
            self.assertEqual(result[name],value)

    def test_unsupported_page_bytes_are_preserved_and_not_editable(self):
        raw = HEADER_V6 + struct.pack('<IBBBB',3,0,1,1,255) + b'xyz'
        page = InkPage.read(raw)
        self.assertTrue(page.warning)
        self.assertEqual(page.to_bytes(), raw)
        with self.assertRaises(ValueError):
            page.add([[1,2,.5]])

    def test_recovery_uses_per_page_blobs_without_rewriting_base(self):
        base = next((Path(self.directory.name)/self.key).glob('*.rmdoc'))
        old = base.read_bytes()
        self.draw()
        self.draw(12,6)
        self.assertEqual(base.read_bytes(),old)
        self.assertEqual(len(self.repo.open(self.key).page(0).strokes),2)
        self.assertEqual(len(list(base.parent.glob('*.rm'))),1)

    def test_malformed_archives_and_unsafe_paths_are_rejected(self):
        for name in ('../bad', '/absolute', 'C:/bad', 'x\\bad'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                read_archive(archive({name:b'data'}))
        with self.assertRaises(ValueError):
            Notebook.read(b'not a zip')
        members = read_archive(self.book.to_bytes())
        content = json.loads(members[self.book.id+'.content'])
        content['pages'] = ['../escape']
        members[self.book.id+'.content'] = json.dumps(content).encode()
        with self.assertRaises(ValueError):
            Notebook.read(archive(members))

    def test_cpages_deleted_pages_order_and_opaque_fields_survive(self):
        members = read_archive(self.book.to_bytes())
        first, second, deleted = self.book.pages[0].id,'second','deleted'
        content = {'fileType':'notebook','unknown':{'keep':42},'cPages':{'uuids':[], 'pages':[
            {'id':second,'idx':{'value':'bb'},'extra':17},
            {'id':deleted,'idx':{'value':'bc'},'deleted':{'value':1}},
            {'id':first,'idx':{'value':'ba'}}]}}
        members[self.book.id+'.content'] = json.dumps(content).encode()
        book = Notebook.read(archive(members))
        self.assertEqual([p.id for p in book.pages],[first,second])
        book.move_page(1,0)
        book.delete_page(1)
        result=Notebook.read(book.to_bytes())
        self.assertEqual(result.pages[0].id,second)
        self.assertEqual(result.pages[0].record['extra'],17)
        self.assertEqual(result.content['unknown'],{'keep':42})

    def test_failed_checkpoint_restores_edit_and_preserves_recovery(self):
        self.draw()
        self.editor.checkpoint = lambda book: (_ for _ in ()).throw(OSError('disk full'))
        with self.assertRaises(OSError):
            self.draw()
        self.assertEqual(len(self.book.page(0).strokes),1)
        self.assertEqual(len(self.repo.open(self.key).page(0).strokes),1)
        for operation in ('undo', 'redo'):
            before = self.editor.snapshot()
            histories = (len(self.editor.undo), len(self.editor.redo))
            with self.assertRaises(OSError):
                self.editor.apply(dict(op=operation))
            self.assertEqual(len(self.book.page(0).strokes), len(before[0][0].ink.strokes))
            self.assertEqual((len(self.editor.undo), len(self.editor.redo)), histories)
            self.editor.checkpoint = lambda book: self.repo.save(self.key, book)
            self.editor.apply(dict(op=operation))
            self.editor.checkpoint = lambda book: (_ for _ in ()).throw(OSError('disk full'))

    def test_bridge_requires_secret_origin_and_ordered_commands(self):
        bridge=Bridge()
        payload=quote(json.dumps(dict(sequence=1,action=dict(op='undo'))))
        self.assertIsNone(bridge.command('https://evil/?command='+payload))
        self.assertEqual(bridge.command(bridge.url+'?command='+payload),{'op':'undo'})
        self.assertIsNone(bridge.command(bridge.url+'?command='+payload))


if __name__=='__main__':
    unittest.main()
