"""Turn diff aggregation, checkpoint persistence and clickable Git preview reuse."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.ide.projects import Project
from features.lm.changes import file_change
from features.lm.domain import conversation, defaults, message, validate_conversation, build_request
from features.lm.project_tools import ProjectTools
from features.lm.storage import Store
from features.lm.ui.page import LMPage
from features.git.diff_view import present_diff


class TurnChangeTests(unittest.TestCase):
    def test_patch_preserves_missing_newlines_and_header_like_source_lines(self):
        change = file_change('folder/main.py', '-- removed\nlast', '++ added\nlast\n')
        view = present_diff(change['patch'])
        self.assertEqual((change['added'], change['removed']), (2, 2))
        self.assertEqual((view.added, view.removed), (2, 2))
        self.assertIn('No newline at end of file', change['patch'])
        self.assertFalse(view.notes)
        self.assertEqual(file_change('x', 'same', 'same')['patch'], '')

    def test_multiple_edits_aggregate_and_external_intervention_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'main.py'
            path.write_text('value = 1\nexisting = 42\n')
            def dispatch(tools, args, cancelled):
                return tools.apply_edit(args, validate_editors=lambda *args: [],
                                        publish_editors=lambda *args: None, cancelled=cancelled)
            tools = ProjectTools(Project('Test', directory), allow_edits=True, edit_dispatch=dispatch)
            def replace(old, new):
                read = json.loads(tools.execute('read_file', json.dumps(dict(path='main.py', start_line=1, end_line=20))))
                return json.loads(tools.execute('edit_file', json.dumps(dict(path='main.py', version=read['version'],
                                                                           old_text=old, new_text=new))))
            self.assertTrue(replace('value = 1', 'value = 2')['edited'])
            self.assertTrue(replace('value = 2', 'value = 3')['edited'])
            self.assertEqual(len(tools.changes), 1)
            diff = tools.changes[0]
            self.assertIn('-value = 1', diff['patch'])
            self.assertIn('+value = 3', diff['patch'])
            self.assertNotIn('value = 2', diff['patch'])
            self.assertEqual((diff['added'], diff['removed']), (1, 1))
            self.assertTrue(replace('value = 3', 'value = 1')['edited'])
            self.assertEqual(tools.changes, [])
            path.write_text('value = 1\nexternal = 4\n')
            self.assertIn('outside', replace('value = 1', 'value = 5')['error'])
            self.assertEqual(tools.changes, [])
            self.assertIn('external', path.read_text())

    def test_legacy_records_and_validation_and_model_context(self):
        data = conversation(defaults(), model='fixture')
        data['messages'] = [message('user', 'First'), message('assistant', 'Done'), message('user', 'Next')]
        self.assertIs(validate_conversation(data), data)
        changes = [file_change('main.py', 'private before\n', 'private after\n')]
        data['messages'][1]['changes'] = changes
        self.assertIs(validate_conversation(data), data)
        payload, _ = build_request(data)
        self.assertNotIn('private before', json.dumps(payload))
        for invalid in (None, 'wrong', [dict(path='main.py')], changes * 2,
                        [dict(changes[0], added=True)], [dict(changes[0], undone='yes')]):
            broken = deepcopy(data)
            broken['messages'][1]['changes'] = invalid
            with self.assertRaises(ValueError):
                validate_conversation(broken)


class ChangesUITests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.page = LMPage(store=self.store)
        self.addCleanup(self.dispose)
        self.page.conversations.new_conversation()
        self.page.resize(1400, 900)
        self.page.show()
        self.change = file_change('source/main.py', 'before = 1\n', 'after = 2\n')
        self.entry = self.page.session.begin_response({})
        self.page.record_changes([self.change])
        self.page.session.complete_response('cancelled', '', {})
        self.page.persist()
        self.page.render()
        self.app.processEvents()

    def dispose(self):
        self.page.prepare_close()
        self.page.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def click_file(self):
        card = self.page.transcript.bubbles[self.entry['id']].changes_card
        from PySide6.QtTest import QTest
        item = card.files.item(0)
        QTest.mouseClick(card.files.viewport(), qt.Qt.MouseButton.LeftButton,
                         pos=card.files.visualItemRect(item).center())
        self.app.processEvents()
        return card

    def test_click_opens_saved_diff_with_git_viewer_and_reopen_retains_it(self):
        self.assertFalse(self.page.changes_pane.isVisible())
        card = self.click_file()
        self.assertIn('Edited 1 file', card.header.text())
        pane = self.page.changes_pane
        self.assertTrue(pane.isVisible())
        from features.git.ui.preview import Preview
        self.assertIsInstance(pane.preview, Preview)
        self.assertEqual(pane.preview.raw_patch, self.change['patch'])
        self.assertFalse(pane.preview.stage_button.isVisible())
        self.assertFalse(pane.preview.ignore_whitespace.isVisible())
        self.assertEqual((pane.preview.diff_view.added, pane.preview.diff_view.removed), (1, 1))
        self.assertTrue(pane.preview.cards.isVisible())
        key = self.page.data['id']
        self.page.session.release_lease()
        self.page.data = None
        self.page.session.open(key)
        self.page.restore()
        self.page.render()
        self.app.processEvents()
        self.assertEqual(self.page.data['messages'][-1]['changes'], [self.change])
        self.click_file()
        self.assertEqual(pane.preview.raw_patch, self.change['patch'])
        self.page.conversations.new_conversation()
        self.page.render()
        self.assertIsNone(pane.key)
        self.assertFalse(pane.isVisible())

    def test_live_edits_are_checkpointed_and_save_failure_stops_generation(self):
        self.page.session.begin_response({})
        self.page.record_changes([self.change])
        saved = self.store.load(self.page.data['id'])
        self.assertEqual(saved['messages'][-1]['status'], 'streaming')
        self.assertEqual(saved['messages'][-1]['changes'], [self.change])
        with patch.object(self.store, 'save', side_effect=OSError('disk full')), patch.object(self.page.client, 'cancel') as cancel:
            self.page.record_changes([self.change])
            cancel.assert_called_once()
        self.assertTrue(self.page.dirty)
        self.assertEqual(self.page.active_message['changes'], [self.change])
        self.assertIn('disk full', self.page.save_error.text())
        self.page.session.complete_response('failed', '', {})
        self.page.persist()

    def test_file_click_toggles_panel_without_selecting_and_close_can_reopen(self):
        card = self.click_file()
        pane = self.page.changes_pane
        self.assertTrue(pane.isVisible())
        self.assertFalse(card.files.selectedItems())
        self.click_file()
        self.assertFalse(pane.isVisible())
        self.click_file()
        self.assertTrue(pane.isVisible())
        close = next(button for button in pane.findChildren(qt.QToolButton)
                     if button.accessibleName() == 'Close changes')
        close.click()
        self.assertFalse(pane.isVisible())
        self.click_file()
        self.assertTrue(pane.isVisible())

    def test_card_collapses_to_three_files_and_view_changes_opens_first(self):
        changes = [file_change(f'source/file{index}.py', 'before\n', 'after\n') for index in range(5)]
        self.entry['changes'] = changes
        self.page.render()
        self.app.processEvents()
        card = self.page.transcript.bubbles[self.entry['id']].changes_card
        self.assertEqual(card.header.text(), 'Edited 5 files')
        self.assertIn('+5', card.totals.text())
        self.assertEqual(card.more_button.text(), 'Show 2 more files ⌄')
        self.assertFalse(card.files.item(2).isHidden())
        self.assertTrue(card.files.item(3).isHidden())
        card.more_button.click()
        self.assertFalse(card.files.item(4).isHidden())
        card.more_button.click()
        self.assertTrue(card.files.item(4).isHidden())
        card.view_button.click()
        self.assertTrue(self.page.changes_pane.isVisible())
        self.assertEqual(self.page.changes_pane.files.currentData(), changes[0]['path'])
        self.page.show_changes(self.entry['id'], changes[1]['path'])
        self.assertTrue(self.page.changes_pane.isVisible())
        self.assertEqual(self.page.changes_pane.files.currentData(), changes[1]['path'])

    def test_context_menu_opens_current_file_in_ide_and_refuses_changed_project(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        root = Path(self.temp.name) / 'project'
        (root / 'source').mkdir(parents=True)
        target = root / self.change['path']
        target.write_text('current content\n')
        project = Project('Fixture', str(root))
        self.page.project_context = SimpleNamespace(projects=lambda: {project.id: project})
        self.entry['request'] = dict(project_id=project.id, project_root=str(root))
        self.page.working_file_opener = Mock(return_value=True)
        card = self.page.transcript.bubbles[self.entry['id']].changes_card
        card.file_menu(card.files.visualItemRect(card.files.item(0)).center())
        menu = qt.QApplication.activePopupWidget()
        self.assertIsInstance(menu, qt.QMenu)
        self.assertEqual(menu.actions()[0].text(), 'Edit in IDE')
        menu.actions()[0].trigger()
        menu.close()
        self.page.working_file_opener.assert_called_once_with(target.resolve())
        self.assertFalse(self.page.changes_pane.isVisible())
        self.entry['request']['project_root'] = str(root / 'different')
        self.page.edit_changed_file(self.entry['id'], self.change['path'])
        self.page.working_file_opener.assert_called_once()
        self.assertIn('root changed', self.page.status.text())
