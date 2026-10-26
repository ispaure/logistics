"""Synthetic native-ink archives, recovery, preservation and editing contracts."""
import json
from io import BytesIO
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import quote
from zipfile import ZipFile, ZipInfo
from uuid import uuid4

from features.notebooks._vendor.rmscene import scene_stream as ss
from features.notebooks._vendor.rmscene.tagged_block_common import HEADER_V6
from features.notebooks._vendor.rmscene.scene_tree import SceneTree
from features.notebooks.notebook import Notebook, read_archive
from features.notebooks.ink import InkPage, TOOLS
from features.notebooks.brushes import BRUSHES, WIDTHS, native_color
from features.notebooks.workspace import Repository, Editor
from features.notebooks.bridge import Bridge


def archive(members):
    out = BytesIO()
    with ZipFile(out, 'w') as z:
        for key, value in members.items():
            # ZipInfo normalizes backslashes on Windows; preserve adversarial
            # entry bytes so unsafe-name assertions exercise the actual reader.
            info = ZipInfo(key)
            info.filename = info.orig_filename = key
            z.writestr(info, value)
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
            for color in BRUSHES[tool]['colors']:
                for width in WIDTHS.values():
                    self.book.page(0).add([[10,20,.25],[30,40,.9]],tool,color,width)
        ink = InkPage.read(self.book.page(0).to_bytes())
        self.assertFalse(ink.warning)
        self.assertEqual(len(ink.strokes), sum(len(b['colors']) * 3 for b in BRUSHES.values()))
        index = 0
        for tool in TOOLS.values():
            for color in BRUSHES[tool]['colors']:
                for width in WIDTHS.values():
                    stroke = ink.strokes[index]
                    self.assertEqual((stroke.tool, stroke.color, stroke.color_rgba, stroke.scale),
                                     (tool, *native_color(tool, color), width))
                    index += 1

    def test_brush_restrictions_reject_commands_without_changing_recovery(self):
        self.draw()
        before = self.book.page(0).to_bytes()
        for tool, color, width in [(17, 5, 2), (17, -1, 2), (18, 0, 2), (18, 12, 2),
                                   (17, 0, .25), (17, 0, 4), (17, 0, True),
                                   (True, 0, 2), (23, False, 2)]:
            with self.subTest(tool=tool, color=color, width=width), self.assertRaises(ValueError):
                self.editor.apply(dict(op='stroke', points=[[20, 30, .5]], tool=tool, color=color, width=width))
            self.assertEqual(self.book.page(0).to_bytes(), before)
            self.assertEqual(self.repo.open(self.key).page(0).to_bytes(), before)

    def test_native_rgba_and_widths_survive_move_copy_undo_and_recovery(self):
        self.editor.apply(dict(op='stroke', points=[[20, 30, .5], [50, 60, .8]], tool=18, color=-1, width=3))
        original = self.book.page(0).strokes[0]
        self.assertEqual(original.color, 9)
        self.assertEqual(original.color_rgba, (255, 195, 140, 255))
        self.assertEqual([p[3] for p in original.points], [60, 60])
        self.editor.apply(dict(op='transform', ids=[original.id], dx=4, dy=5))
        moved = self.repo.open(self.key).page(0).strokes[0]
        self.assertEqual(moved.color_rgba, original.color_rgba)
        self.assertEqual(moved.points[0], [24, 35, 128 / 255, 60])
        self.editor.apply(dict(op='undo'))
        self.assertEqual(self.book.page(0).strokes[0].points, original.points)
        target = Notebook.new('Copy')
        target.copy_page(self.book, 0)
        copied = Notebook.read(target.to_bytes()).page(1).strokes[0]
        self.assertEqual(copied.color_rgba, original.color_rgba)
        self.assertEqual(copied.points, original.points)

    def test_native_width_dynamics_are_tool_specific(self):
        from features.notebooks.brushes import stroke_points
        samples = [[20, 30, .1], [60, 30, .9], [60, 70, .9]]
        fine = stroke_points(samples, 17, 2)
        mechanical = stroke_points(samples, 13, 2)
        self.assertEqual({p[3] for p in fine}, {2})
        self.assertEqual({p[3] for p in mechanical}, {1.5})
        for tool in (12, 14, 15, 16, 23):
            widths = [p[3] for p in stroke_points(samples, tool, 2)]
            self.assertLess(widths[0], widths[1])
        diagonal = [[20, 20, .6], [40, 40, .6], [60, 20, .6]]
        calligraphy = stroke_points(diagonal, 21, 2)
        self.assertLess(calligraphy[1][3], calligraphy[2][3])

    def test_shader_uses_its_native_palette_and_color_specific_alpha(self):
        # Independent native ARGB values from the color definitions, not
        # derived from the application's palette or native_color helper.
        native = {1: 0x40211E1C, 6: 0x4D304AE0, 7: 0x66C23132,
                  10: 0x8091DA71, 13: 0x73FAE719, 11: 0x6674D2E8,
                  12: 0x80C07FD2, -1: 0x73FEB200}
        self.assertEqual(set(BRUSHES[23]['colors']), set(native))
        for choice, argb in native.items():
            self.book.page(0).add([[20, 30, .5]], tool=23, color=choice)
            stroke = InkPage.read(self.book.page(0).to_bytes()).strokes[-1]
            self.assertEqual(stroke.color, 9)
            self.assertEqual(stroke.color_rgba,
                             ((argb >> 16) & 255, (argb >> 8) & 255, argb & 255, argb >> 24))
        for choice in (0, 2, 5):
            with self.assertRaises(ValueError):
                self.book.page(0).add([[20, 30, .5]], tool=23, color=choice)

    def test_imported_native_erasers_are_not_painted_as_black_fineliner_ink(self):
        from features.notebooks.ink import encode
        from features.notebooks._vendor.rmscene import scene_items as si
        ink = InkPage.blank()
        ink.add([[20, 30, .5], [50, 60, .8]])
        blocks = list(ss.read_blocks(BytesIO(ink.to_bytes())))
        line = next(b.item.value for b in blocks if isinstance(b, ss.SceneLineItemBlock))
        for tool in (si.Pen.ERASER, si.Pen.ERASER_AREA):
            line.tool = tool
            raw = encode(blocks)
            imported = InkPage.read(raw)
            self.assertIn('eraser objects', imported.warning)
            self.assertFalse(imported.strokes)
            self.assertEqual(imported.to_bytes(), raw)

    def test_imported_custom_rgba_and_widths_are_preserved_outside_creation_palette(self):
        from features.notebooks.ink import encode
        ink = InkPage.blank()
        ink.add([[20, 30, .5], [50, 60, .8]])
        blocks = list(ss.read_blocks(BytesIO(ink.to_bytes())))
        line = next(b.item.value for b in blocks if isinstance(b, ss.SceneLineItemBlock))
        line.color_rgba = (12, 34, 56, 117)
        line.thickness_scale = 2.5
        for point in line.points:
            point.width = 37
        raw = encode(blocks)
        imported = InkPage.read(raw)
        self.assertEqual(imported.to_bytes(), raw)
        stroke = imported.strokes[0]
        self.assertEqual(stroke.payload()['color_rgba'], (12, 34, 56, 117))
        stroke.points = [[x + 4, y + 5, p, w] for x, y, p, w in stroke.points]
        moved = InkPage.read(imported.to_bytes()).strokes[0]
        self.assertEqual(moved.color_rgba, (12, 34, 56, 117))
        self.assertEqual(moved.scale, 2.5)
        self.assertEqual([p[3] for p in moved.points], [9.25, 9.25])

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

    def test_empty_damaged_ink_is_not_replaced_with_a_blank_scene(self):
        members = read_archive(self.book.to_bytes())
        path = f'{self.book.id}/{self.book.pages[0].id}.rm'
        members[path] = b''
        imported = Notebook.read(archive(members))
        self.assertTrue(imported.page(0).warning)
        key = self.repo.create(imported)
        self.assertEqual(read_archive(self.repo.open(key).to_bytes())[path], b'')

    def test_invalid_scale_and_nested_groups_preserve_bytes_read_only(self):
        from features.notebooks.ink import encode
        from features.notebooks._vendor.rmscene import scene_items as si
        from features.notebooks._vendor.rmscene.crdt_sequence import CrdtSequenceItem
        from features.notebooks._vendor.rmscene.tagged_block_common import CrdtId, LwwValue
        ink = InkPage.blank()
        ink.add([[10, 20, .5]])
        blocks = list(ss.read_blocks(BytesIO(ink.to_bytes())))
        line = next(b for b in blocks if isinstance(b, ss.SceneLineItemBlock))
        line.item.value.thickness_scale = float('inf')
        invalid = encode(blocks)
        preserved = InkPage.read(invalid)
        self.assertIn('thickness scale', preserved.warning)
        self.assertEqual(preserved.to_bytes(), invalid)
        node, layer, end = CrdtId(2, 1), CrdtId(0, 11), CrdtId(0, 0)
        nested = InkPage.blank().raw + encode([
            ss.AuthorIdsBlock({2: uuid4()}),
            ss.SceneTreeBlock(node, end, True, layer),
            ss.TreeNodeBlock(si.Group(node, label=LwwValue(CrdtId(2, 3), 'Nested'))),
            ss.SceneGroupItemBlock(layer, CrdtSequenceItem(CrdtId(2, 2), end, end, 0, node)),
        ])[len(HEADER_V6):]
        preserved = InkPage.read(nested)
        self.assertIn('Nested ink groups', preserved.warning)
        self.assertEqual(preserved.to_bytes(), nested)

    def test_edit_limit_failure_keeps_previous_ink_editable_and_recoverable(self):
        self.draw()
        with patch('features.notebooks.ink.MAX_PAGE_POINTS', 3):
            with self.assertRaisesRegex(ValueError, 'Too many ink points'):
                self.draw()
            restored = self.repo.open(self.key)
            self.assertFalse(restored.page(0).warning)
            self.assertEqual(len(restored.page(0).strokes), 1)
            self.assertFalse(self.book.page(0).warning)
            self.assertEqual(len(self.book.page(0).strokes), 1)
        self.draw()
        self.assertEqual(len(self.repo.open(self.key).page(0).strokes), 2)

    def test_cleanup_failure_after_manifest_publication_is_not_a_failed_edit(self):
        with patch.object(Path, 'iterdir', side_effect=OSError('temporarily unavailable')):
            self.draw()
        self.assertEqual(len(self.book.page(0).strokes), 1)
        self.assertEqual(len(self.repo.open(self.key).page(0).strokes), 1)
        self.editor.apply(dict(op='undo'))
        self.assertEqual(len(self.repo.open(self.key).page(0).strokes), 0)

    def test_modern_page_delete_undo_redo_and_reorder_keep_recoverable_order(self):
        self.book.add_page()
        members = read_archive(self.book.to_bytes())
        content = json.loads(members[self.book.id + '.content'])
        ids = content.pop('pages')
        content['cPages'] = dict(pages=[dict(id=key, idx=dict(value=chr(98+i))) for i,key in enumerate(ids)])
        members[self.book.id + '.content'] = json.dumps(content).encode()
        book = Notebook.read(archive(members))
        key = self.repo.create(book)
        editor = Editor(book, lambda current: self.repo.save(key, current))
        for op, expected in [('delete-page', ids[1:]), ('undo', ids), ('redo', ids[1:]), ('undo', ids)]:
            editor.apply(dict(op=op))
            self.assertEqual([p.id for p in self.repo.open(key).pages], expected)
            self.assertEqual([p.id for p in Notebook.read(book.to_bytes()).pages], expected)

    def test_notebook_titles_cannot_replace_canvas_template_instructions(self):
        from features.notebooks.canvas import editor_html
        title = '__BRIDGE__ __MAX_COMMAND__ __SEND_COMMAND__ __STATE__ </script>'
        self.book.metadata['visibleName'] = title
        html = editor_html(self.editor.state(), 'logistics-notebook://fixture/')
        encoded = html.split("'use strict';let state=", 1)[1].split(',bridge=', 1)[0]
        self.assertEqual(json.loads(encoded)['name'], title)

    def test_invalid_page_operations_do_not_partially_mutate_the_notebook(self):
        self.book.add_page()
        before = [p.id for p in self.book.pages]
        members = dict(self.book.members)
        for target in (-1, 999, 1.5, True, '1'):
            for operation in (lambda: self.book.move_page(0, target),
                              lambda: self.book.add_page(target),
                              lambda: self.book.copy_page(self.book, 0, target)):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    operation()
                self.assertEqual([p.id for p in self.book.pages], before)
                self.assertEqual(self.book.members, members)


if __name__=='__main__':
    unittest.main()
