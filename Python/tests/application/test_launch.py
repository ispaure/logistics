"""Startup initializes Qt before hooks that can display error dialogs."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from unittest.mock import Mock, patch
import unittest

import launch
from desktop import __main__ as module_launcher


class LaunchTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(launch, 'IndexService')
        self.service = patcher.start().return_value
        self.addCleanup(patcher.stop)
        for name in ('apply_styling', 'initialize_settings'):
            patcher = patch.object(launch, name)
            patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(launch.registry, 'load_feature_preferences')
        patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(launch.pyside.QTimer, 'singleShot')
        self.schedule = patcher.start(); self.addCleanup(patcher.stop)

    def test_independent_launches_start_their_own_index_participant(self):
        with patch.object(launch, 'log'), patch.object(launch.pyside, 'initialize_q_app') as app, \
                patch.object(launch.registry, 'load_feature_preferences'), \
                patch.object(launch.registry, 'initialize_features'), \
                patch.object(launch, 'apply_theme'), patch.object(launch, 'MainWindow') as window:
            app.return_value.exec.return_value = 0
            window.return_value.pending_update = None
            self.assertEqual(launch.main(), 0)
            self.assertEqual(launch.main(), 0)
        self.assertEqual(window.call_count, 2)
        self.assertEqual(self.service.start.call_count, 2)
        self.assertEqual(self.service.stop.call_count, 2)

    def test_qt_precedes_feature_initialization_and_window_display(self):
        events = []
        app = Mock()
        app.exec.side_effect = lambda: events.append('event loop') or 7
        window = Mock(pending_update=None)
        window.display_ui.side_effect = lambda: events.append('display window')
        with patch.object(launch, 'log'), patch.object(
                launch.pyside, 'initialize_q_app',
                side_effect=lambda: events.append('create app') or app), patch.object(
                launch.registry, 'initialize_features',
                side_effect=lambda: events.append('initialize features')), patch.object(
                launch, 'MainWindow',
                side_effect=lambda: events.append('create window') or window):
            self.assertEqual(launch.main(), 7)
        self.service.stop.assert_called_once_with()
        self.assertEqual(events, ['create app', 'initialize features', 'create window',
                                  'display window', 'event loop'])

    def test_failed_feature_initialization_does_not_construct_window(self):
        with patch.object(launch, 'log'), patch.object(
                launch.pyside, 'initialize_q_app') as create_app, patch.object(
                launch.registry, 'initialize_features', side_effect=RuntimeError('startup failed')), patch.object(
                launch, 'MainWindow') as create_window:
            with self.assertRaisesRegex(RuntimeError, 'startup failed'):
                launch.main()
        self.service.stop.assert_called_once_with()
        create_app.assert_called_once_with()
        create_window.assert_not_called()
        create_app.return_value.exec.assert_not_called()
        self.schedule.assert_not_called()

    def test_module_launcher_uses_the_application_entry_point(self):
        self.assertIs(module_launcher.main, launch.main)

    def test_windows_console_minimizes_after_window_display_in_event_loop(self):
        events = []
        callbacks = []
        window = Mock(pending_update=None)
        window.display_ui.side_effect = lambda: events.append('landing displayed')
        self.schedule.side_effect = lambda delay, owner, callback: callbacks.append(callback)

        def event_loop():
            events.append('event loop')
            for callback in callbacks:
                callback()
            return 0

        with patch.object(launch, 'get_os', return_value=launch.OS.WIN), \
                patch.object(launch, 'minimize_console_window',
                             side_effect=lambda: events.append('console minimized')) as minimize, \
                patch.object(launch.pyside, 'initialize_q_app') as app, \
                patch.object(launch.registry, 'initialize_features'), \
                patch.object(launch, 'apply_theme'), patch.object(launch, 'MainWindow', return_value=window):
            app.return_value.exec.side_effect = event_loop
            self.assertEqual(launch.main(), 0)
            self.schedule.assert_called_once_with(0, window.dlg, minimize)
        self.assertEqual(events, ['landing displayed', 'event loop', 'console minimized'])

    def test_other_platforms_do_not_schedule_windows_console_helper(self):
        for platform in (launch.OS.MAC, launch.OS.LINUX):
            with self.subTest(platform=platform), \
                    patch.object(launch, 'get_os', return_value=platform), \
                    patch.object(launch.pyside, 'initialize_q_app') as app, \
                    patch.object(launch.registry, 'initialize_features'), \
                    patch.object(launch, 'apply_theme'), patch.object(launch, 'MainWindow') as window:
                window.return_value.pending_update = None
                app.return_value.exec.return_value = 0
                self.assertEqual(launch.main(), 0)
        self.schedule.assert_not_called()

    def test_update_helper_starts_after_event_loop_and_index_shutdown(self):
        events = []
        request = object()
        self.service.stop.side_effect = lambda: events.append('index stopped')
        with patch.object(launch, 'log'), patch.object(launch.pyside, 'initialize_q_app') as app, \
                patch.object(launch.registry, 'initialize_features'), patch.object(launch, 'apply_theme'), \
                patch.object(launch, 'MainWindow') as window, \
                patch('services.updates.launch_helper', side_effect=lambda value: events.append(('helper', value))):
            window.return_value.pending_update = request
            app.return_value.exec.side_effect = lambda: events.append('event loop exited') or 0
            self.assertEqual(launch.main(), 0)
        self.assertEqual(events, ['event loop exited', 'index stopped', ('helper', request)])
