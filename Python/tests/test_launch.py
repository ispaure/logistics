"""Startup initializes Qt before hooks that can display error dialogs."""

from unittest.mock import Mock, patch
import unittest

import launch
from ui_new import __main__ as module_launcher


class LaunchTests(unittest.TestCase):
    def test_qt_precedes_feature_initialization_and_window_display(self):
        events = []
        app = Mock()
        app.exec.side_effect = lambda: events.append('event loop') or 7
        window = Mock()
        window.display_ui.side_effect = lambda: events.append('display window')
        with patch.object(launch, 'log'), patch.object(
                launch.pyside, 'initialize_q_app',
                side_effect=lambda: events.append('create app') or app), patch.object(
                launch.registry, 'initialize_features',
                side_effect=lambda: events.append('initialize features')), patch.object(
                launch, 'MainWindow',
                side_effect=lambda: events.append('create window') or window):
            self.assertEqual(launch.main(), 7)
        self.assertEqual(events, ['create app', 'initialize features', 'create window',
                                  'display window', 'event loop'])

    def test_failed_feature_initialization_does_not_construct_window(self):
        with patch.object(launch, 'log'), patch.object(
                launch.pyside, 'initialize_q_app') as create_app, patch.object(
                launch.registry, 'initialize_features', side_effect=RuntimeError('startup failed')), patch.object(
                launch, 'MainWindow') as create_window:
            with self.assertRaisesRegex(RuntimeError, 'startup failed'):
                launch.main()
        create_app.assert_called_once_with()
        create_window.assert_not_called()
        create_app.return_value.exec.assert_not_called()

    def test_module_launcher_uses_the_application_entry_point(self):
        self.assertIs(module_launcher.main, launch.main)
