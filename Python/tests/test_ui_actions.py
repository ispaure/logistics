"""Contributed actions retain confirmation, workflow and refresh behavior."""

from unittest.mock import Mock, patch
import unittest

from features.contributions import DebugActionContribution, UIAction
from ui_new.actions import execute_action


class ActionExecutionTests(unittest.TestCase):
    def test_disabled_actions_never_execute_callbacks_or_workflows(self):
        callback = Mock()
        with patch('ui_new.actions.workflows.open_workflow') as workflow:
            self.assertFalse(execute_action(UIAction('Disabled', callback, enabled=False)))
            self.assertFalse(execute_action(UIAction('Disabled dialog', workflow_id='dialog', enabled=False)))
        callback.assert_not_called()
        workflow.assert_not_called()

    def test_workflow_receives_context_without_extra_confirmation(self):
        parent, data, refresh = object(), object(), Mock()
        with patch('ui_new.actions.workflows.open_workflow') as workflow, patch(
                'ui_new.actions.ui.display_msg_box_ok_cancel') as confirm:
            self.assertTrue(execute_action(UIAction('Dialog', workflow_id='dialog', workflow_data=data),
                                           parent, refresh=refresh))
        workflow.assert_called_once_with('dialog', data=data, parent=parent)
        confirm.assert_not_called()
        refresh.assert_not_called()

    def test_cancelled_destructive_callback_does_not_run_or_refresh(self):
        callback, refresh = Mock(), Mock()
        with patch('ui_new.actions.ui.display_msg_box_ok_cancel', return_value=False) as confirm:
            self.assertFalse(execute_action(UIAction('Delete', callback, destructive=True),
                                            subject='Example', refresh=refresh))
        self.assertIn('for "Example"', confirm.call_args.args[1])
        callback.assert_not_called()
        refresh.assert_not_called()

    def test_destructive_callback_finishes_before_refresh(self):
        events = []
        action = UIAction('Change', lambda: events.append('callback'), destructive=True)
        with patch('ui_new.actions.ui.display_msg_box_ok_cancel', return_value=True):
            self.assertTrue(execute_action(action, refresh=lambda: events.append('refresh')))
        self.assertEqual(events, ['callback', 'refresh'])

    def test_nondestructive_callback_does_not_prompt_or_refresh(self):
        callback, refresh = Mock(), Mock()
        with patch('ui_new.actions.ui.display_msg_box_ok_cancel') as confirm:
            self.assertTrue(execute_action(UIAction('Open', callback), refresh=refresh))
        callback.assert_called_once_with()
        confirm.assert_not_called()
        refresh.assert_not_called()

    def test_debug_confirmation_retains_system_configuration_scope(self):
        action = DebugActionContribution('Configure', Mock(), destructive=True)
        with patch('ui_new.actions.ui.display_msg_box_ok_cancel', return_value=True) as confirm:
            execute_action(action)
        self.assertEqual(confirm.call_args.args[0], 'Confirm Debug Action')
        self.assertIn('files or system configuration', confirm.call_args.args[1])

    def test_failed_callbacks_do_not_refresh_or_hide_the_exception(self):
        refresh = Mock()
        action = UIAction('Fail', Mock(side_effect=RuntimeError('failure')), destructive=True)
        with patch('ui_new.actions.ui.display_msg_box_ok_cancel', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'failure'):
                execute_action(action, refresh=refresh)
        refresh.assert_not_called()
