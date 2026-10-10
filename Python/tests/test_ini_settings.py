"""Logistics compatibility imports and existing feature configuration readers."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from commonUtils.fileTypes.iniType import INIFile
from ui_new.settings.ini_editor import INISettingsEditor
from commonUtils.ui.ini_editor import INISettingsEditor as SharedINISettingsEditor


class CompatibilityTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'config.ini'

    def test_logistics_wrapper_preserves_typed_default(self):
        self.path.write_text('[S]\non_bool = true\n')
        editor = INISettingsEditor(self.path)
        self.addCleanup(editor.deleteLater)
        self.assertIsInstance(editor, SharedINISettingsEditor)
        self.assertIsInstance(editor.fields['S','on_bool'], qt.QCheckBox)

    def test_schema_imports_are_compatibility_aliases(self):
        from ui_new.settings import ini_schema as old
        from commonUtils.configuration import ini_schema as shared
        self.assertIs(old.parse_value, shared.parse_value)
        self.assertIs(old.validate_values, shared.validate_values)

    def test_feature_readers_support_typed_and_legacy_keys(self):
        from features.links import configuration as links
        from features.smart_home import configuration as smart
        for suffix in ('', '_str'):
            self.path.write_text(f'[URLs]\ngoogle{suffix}=https://example.com\n[ResolveIP]\nhost{suffix}=127.0.0.1\n[PhilipsHue]\nbridge_address{suffix}=127.0.0.2\n')
            with patch.object(links, 'get_config_file_path', return_value=self.path), patch.object(smart, 'get_config_file_path', return_value=self.path):
                self.assertEqual(links.get_url('google'), 'https://example.com')
                self.assertEqual(links.get_resolve_ip('host'), '127.0.0.1')
                self.assertEqual(smart.get_philips_hue_bridge_address(), '127.0.0.2')


if __name__ == '__main__':
    unittest.main()
