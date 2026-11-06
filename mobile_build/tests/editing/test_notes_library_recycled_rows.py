"""Virtual tree projection preserves Notes actions and retires stale row sources."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from commonUtils.testing.stages import TestStage
from mobile.composition import presentation
from mobile.obsidian import open_vault
from mobile.recycled_file_list import RecycledFileList
from features.notes_library.mobile.tree_rows import NativeTreeRows
from mobile_build.tests.documents import test_obsidian as fixtures

TEST_STAGE = TestStage.REGRESSION


class RecycledNotesRowsTests(unittest.TestCase):
    setUp = fixtures.ObsidianTests.setUp
    tearDown = fixtures.ObsidianTests.tearDown
    run_async = fixtures.ObsidianTests.run_async

    async def library(self, count=40):
        folder = self.vault / 'Many'
        folder.mkdir()
        for index in range(count):
            (folder / f'Note {index}.md').write_text('# Fixture')
        (folder / 'Child').mkdir()
        (folder / 'Child' / 'Child.md').write_text('# Landing')
        factory = presentation.notes_host
        with patch.object(presentation, 'notes_host', side_effect=lambda app: replace(factory(app),
                tree_rows=lambda owner: NativeTreeRows(owner, RecycledFileList))):
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
        owner.sidebar.show_sidebar()
        return owner

    def test_expansion_publishes_records_without_constructing_row_widgets(self):
        async def exercise():
            owner = await self.library()
            rows, widget = owner.rows, owner.rows.native_list
            with patch.object(owner, 'bind_file_hold', side_effect=AssertionError('Per-row binding')), \
                 patch.object(owner, 'host', replace(owner.host, entry_icon=Mock(side_effect=AssertionError('Per-row icon')))), \
                 patch.object(rows, 'add', wraps=rows.add) as publish:
                await owner.toggle_folder('Vault/Many')
                self.assertEqual(publish.call_count, 1, 'Cold folder published twice')
            children = rows.children
            self.assertEqual(len([row for row in children if row.path.startswith('Vault/Many/')]), 41)
            self.assertEqual(owner._row_cache, {})
            self.assertEqual(next(row.tree_depth for row in children if row.path.endswith('/Note 0.md')), 1)
            self.assertTrue(next(row.tree_landing for row in children if row.path.endswith('/Child')))
            await owner.toggle_folder('Vault/Many')
            await owner.toggle_folder('Vault/Many')
            self.assertIs(owner.rows, rows)
            self.assertIs(owner.rows.native_list, widget)
            owner.dispose()
        self.run_async(exercise())

    def test_landing_activation_and_disclosure_are_distinct(self):
        async def exercise():
            owner = await self.library()
            await owner.toggle_folder('Vault/Many')
            rows = owner.rows
            child = next(row for row in rows.children if row.path.endswith('/Child'))
            with patch.object(owner, 'open_note', new=AsyncMock()) as opened, \
                 patch.object(owner, 'toggle_folder', new=AsyncMock()) as expanded:
                await rows.activate(child)
                opened.assert_awaited_once_with('Vault/Many/Child/Child.md')
                expanded.assert_not_awaited()
                rows.toggle(child)
                await asyncio.gather(*tuple(rows.tasks))
                expanded.assert_awaited_once_with('Vault/Many/Child')
            owner.dispose()
        self.run_async(exercise())

    def test_replaced_or_hidden_rows_cannot_activate_or_open_actions(self):
        async def exercise():
            owner = await self.library()
            await owner.toggle_folder('Vault/Many')
            rows = owner.rows
            old = next(row for row in rows.children if not row.folder)
            owner.render_tree()
            current = next(row for row in rows.children if not row.folder)
            with patch.object(owner, 'open_note', new=AsyncMock()) as opened, \
                 patch.object(owner, 'file_actions', new=AsyncMock()) as actions:
                await rows.activate(old)
                await rows.actions(old)
                self.assertFalse(rows.start_drag(old))
                self.assertFalse(rows.can_drop(old))
                owner.select_panel_tab('Search')
                await rows.activate(current)
                await rows.actions(current)
                opened.assert_not_awaited()
                actions.assert_not_awaited()
                owner.select_panel_tab('Files')
                await rows.activate(current)
                opened.assert_not_awaited()
                restored = next(row for row in rows.children if row.path == current.path)
                await rows.activate(restored)
                opened.assert_awaited_once_with(current.path)
            owner.dispose()
        self.run_async(exercise())

    def test_calendar_detail_and_detached_cells_cannot_dispatch_file_actions(self):
        async def exercise():
            owner = await self.library()
            owner.reflow(320)
            owner.sidebar.show_sidebar()
            rows = owner.rows
            with patch.object(owner, 'open_note', new=AsyncMock()) as opened:
                row = next(row for row in rows.children if not row.folder)
                owner.select_panel_tab('Calendar')
                await rows.activate(row)
                opened.assert_not_awaited()
                owner.select_panel_tab('Files')
                row = next(row for row in rows.children if not row.folder)
                owner.sidebar.show_detail()
                await rows.activate(row)
                opened.assert_not_awaited()
                owner.sidebar.show_sidebar()
                native = Mock(isAttachedToWindow=Mock(return_value=True), isShown=Mock(return_value=False))
                with patch.object(rows.native_list._impl, 'native', native, create=True):
                    await rows.activate(row)
                opened.assert_not_awaited()
                await rows.activate(row)
                opened.assert_awaited_once_with(row.path)
            owner.dispose()
        self.run_async(exercise())

    def test_uikit_table_must_be_attached_and_visible_before_dispatch(self):
        async def exercise():
            owner = await self.library()
            rows = owner.rows
            parent = SimpleNamespace(superview=None, alpha=1, isHidden=Mock(return_value=False))
            native = Mock(window=None, superview=parent, alpha=1, isHidden=Mock(return_value=False))
            backend = type('DetailedList', (), {'__module__': 'toga_iOS.widgets.detailedlist'})
            with patch.object(rows.native_list.factory, 'DetailedList', backend), \
                    patch.object(rows.native_list._impl, 'native', native, create=True):
                self.assertFalse(rows.active())
                native.window = object()
                self.assertTrue(rows.active())
                native.isHidden.return_value = True
                self.assertFalse(rows.active())
                native.isHidden.return_value = False
                parent.isHidden.return_value = True
                self.assertFalse(rows.active())
            owner.dispose()
        self.run_async(exercise())

    def test_actions_and_selection_never_activate_adjacent_filename(self):
        async def exercise():
            owner = await self.library()
            rows = owner.rows
            row = rows.children[0]
            with patch.object(owner, 'open_note', new=AsyncMock()) as opened, \
                 patch.object(owner, 'file_actions', new=AsyncMock()) as actions:
                owner.selected_path = row.path
                owner.update_tree_selection()
                rows.context(rows.native_list, row)
                await asyncio.gather(*tuple(rows.tasks))
                actions.assert_awaited_once_with(row.path)
                opened.assert_not_awaited()
            owner.dispose()
        self.run_async(exercise())

    def test_native_list_exposes_all_rows_and_retires_sources(self):
        async def exercise():
            owner = await self.library(count=80)
            await owner.toggle_folder('Vault/Many')
            rows = owner.rows
            note_paths = [row.path for row in rows.children if row.path.startswith('Vault/Many/Note ')]
            self.assertCountEqual(note_paths, [f'Vault/Many/Note {index}.md' for index in range(80)])
            self.assertEqual(owner._row_cache, {})
            all_rows = [state['rows'] for state in owner._row_panels.values()]
            owner.dispose()
            for source in all_rows:
                self.assertEqual(source.children, [])
                self.assertTrue(source.closed)
                self.assertIsNone(source.native_list.tree_actions)
        self.run_async(exercise())

    def test_drag_uses_existing_opaque_token_and_revalidates_targets(self):
        async def exercise():
            owner = await self.library()
            await owner.toggle_folder('Vault/Many')
            rows = owner.rows
            source = next(row for row in rows.children if row.path.endswith('Note 0.md'))
            target = next(row for row in rows.children if row.path.endswith('/Child'))
            self.assertEqual(rows.drag_token, owner.file_drag.token)
            self.assertTrue(rows.start_drag(source))
            self.assertTrue(rows.can_drop(target))
            with patch.object(owner.file_drag, 'drop', new=Mock(return_value=True)) as drop:
                self.assertTrue(rows.drop(target))
                drop.assert_called_once_with(target.path)
            rows.end_drag()
            self.assertFalse(rows.can_drop(target))
            owner.dispose()
        self.run_async(exercise())
