"""Retained Workspaces row identity, callback capture and menu retirement."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from unittest.mock import AsyncMock, Mock, patch

from mobile.folder_tree_view import FolderTreeView


def local(name):
    return dict(name=name, source='Local', kind='local', value=name)


class FolderTreeViewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.browse = AsyncMock()
        self.choose, self.actions, self.invoke, self.context = (Mock() for _ in range(4))
        self.view = FolderTreeView(browse=self.browse, choose=self.choose,
            actions=self.actions, invoke=self.invoke, native_context=self.context)

    def render(self, *names):
        self.view.render({name: local(name) for name in names}, 'Local', set(), set())

    async def test_unchanged_snapshot_keeps_controls_menus_and_geometry_without_remounting(self):
        self.render('Team-Books', 'Team-Notes')
        records = dict(self.view.nodes)
        guides = {path: row.guide for path, row in records.items()}
        with patch('toga.Box.insert', side_effect=AssertionError('Remounted unchanged child')), \
                patch('toga.Box.remove', side_effect=AssertionError('Detached unchanged child')):
            self.render('Team-Notes', 'Team-Books')
        self.assertEqual(self.view.nodes, records)
        for path, record in records.items():
            self.assertIs(self.view.nodes[path], record)
            self.assertIs(record.guide, guides[path])
        for callback in (self.browse, self.choose, self.actions, self.invoke, self.context):
            callback.assert_not_called()

    async def test_removed_descendants_retire_menus_and_leave_retained_parent_usable(self):
        self.render('Team', 'Team-Books', 'Other')
        parent, child, other = (self.view.nodes[path] for path in
            [('Team',), ('Team', 'Books'), ('Other',)])
        with patch.object(child.commands, 'dispose', wraps=child.commands.dispose) as dispose:
            self.render('Team', 'Other')
        dispose.assert_called_once()
        self.assertTrue(child.commands.disposed)
        self.assertEqual(list(parent.child_content.children), [])
        self.assertIs(self.view.nodes[('Team',)], parent)
        self.assertIs(self.view.nodes[('Other',)], other)
        self.assertEqual(set(self.view.buttons), {'Team', 'Other'})
        await parent.button.on_press()
        self.browse.assert_awaited_once_with('Team')

    async def test_group_to_selectable_and_back_replaces_only_that_row_and_retires_its_menu(self):
        self.render('Team-Books')
        group, books = self.view.nodes[('Team',)], self.view.nodes[('Team', 'Books')]
        self.render('Team', 'Team-Books')
        selectable = self.view.nodes[('Team',)]
        self.assertIsNot(selectable, group)
        self.assertIs(self.view.nodes[('Team', 'Books')], books)
        with patch.object(selectable.commands, 'dispose', wraps=selectable.commands.dispose) as dispose:
            self.render('Team-Books')
        dispose.assert_called_once()
        self.assertIs(self.view.nodes[('Team', 'Books')], books)
        self.assertIsNot(self.view.nodes[('Team',)], selectable)
        self.assertIn(('Team',), self.view.tree_buttons)

    async def test_actions_resolve_at_invocation_and_browse_captures_each_folder_identity(self):
        self.render('Team-Books', 'Other-Books')
        for name, button in self.view.buttons.items():
            await button.on_press()
            self.browse.assert_awaited_with(name)
        record = self.view.nodes[('Team', 'Books')]
        self.actions.assert_not_called()
        expected = [('Current command', Mock())]
        self.actions.return_value = expected
        self.assertEqual(record.commands.load_actions(), expected)
        self.actions.assert_called_once_with('Team-Books')
        self.actions.return_value = []
        self.assertEqual(record.commands.load_actions(), [])
        record.commands.fallback()
        self.choose.assert_called_once_with('Team-Books')

    async def test_empty_and_browse_all_controls_reuse_identity_across_source_refreshes(self):
        entries = {'All files': dict(local('All files'), browser_root=True)}
        self.view.render(entries, 'Local', set(), set())
        empty, row = self.view.content.children
        browse = self.view.buttons['All files']
        self.assertIn(browse, row.children)
        self.assertIsNone(self.view.nodes[('All files',)].menu)
        await browse.on_press()
        self.browse.assert_awaited_once_with('All files')
        self.view.render({}, 'Local', set(), set())
        self.assertEqual(list(self.view.content.children), [empty])
        self.assertFalse(self.view.buttons)
        self.assertFalse(self.view.nodes)
