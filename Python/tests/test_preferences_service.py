"""Reset orchestration distinguishes rollback from post-commit view failures."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from commonUtils.configuration.monitor import settings_monitor
from services.preferences import reset_personal_preferences


class PreferencesServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.personal = self.root / 'configuration' / 'configFile.ini'
        self.personal.parent.mkdir()
        self.personal.write_text('[FeatureDefaults]\ndisabled_list-str=["blender"]\n')
        patcher = patch('features.settings.preferences_path', return_value=self.root / 'preferences.ini')
        patcher.start(); self.addCleanup(patcher.stop)

    def test_tools_are_notified_only_after_storage_and_activation_commit(self):
        calls = []
        unsubscribe = settings_monitor().subscribe(self.personal, lambda: calls.append(('notify', self.personal.exists())))
        self.addCleanup(unsubscribe)
        with patch('services.preferences.registry.reset_feature_defaults', side_effect=lambda: calls.append(('features', False))):
            result = reset_personal_preferences(refresh_callbacks=(lambda: calls.append(('view', False)),))
        self.assertEqual(calls, [('features', False), ('notify', False), ('view', False)])
        self.assertEqual(result.refresh_errors, ())

    def test_activation_failure_rolls_back_without_publishing_success(self):
        before = self.personal.read_bytes()
        callback = Mock()
        unsubscribe = settings_monitor().subscribe(self.personal, callback)
        self.addCleanup(unsubscribe)
        with patch('services.preferences.registry.reset_feature_defaults', side_effect=ValueError('Cannot activate')):
            with self.assertRaises(ValueError):
                reset_personal_preferences(refresh_callbacks=(callback,))
        self.assertEqual(self.personal.read_bytes(), before)
        callback.assert_not_called()

    def test_view_failure_reports_committed_reset_and_continues_other_refreshes(self):
        first = Mock(side_effect=ValueError('Cannot reload editor'))
        second = Mock()
        with patch('services.preferences.registry.reset_feature_defaults'):
            result = reset_personal_preferences(refresh_callbacks=(first, second))
        self.assertFalse(self.personal.exists())
        self.assertEqual(result.refresh_errors, ('Cannot reload editor',))
        second.assert_called_once()
