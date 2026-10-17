"""Settings help preserves preference values; About uses the installed payload."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from logisticsmobile.app import LogisticsMobile
from logisticsmobile.settings_ui import build_information


class SettingsUITests(unittest.TestCase):
    def test_help_order_dialog_and_about_at_bottom(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile', version='0.1.5')
            app.show_settings()
            box = app.body.children[0].content
            for switch, title in ((app.document_cards_choice, 'Document card overview'),
                                  (app.restore_choice, 'Restore last document'),
                                  (app.clear_documents_choice, 'Close saved documents on restart')):
                label, info, control = switch.parent.children
                self.assertEqual(label.text.replace('\n', ' '), title)
                self.assertEqual(info.text, 'ⓘ')
                self.assertIs(control, switch)
                previous = switch.value
                with patch.object(app.main_window, 'dialog', new=AsyncMock()) as dialog, \
                        patch('logisticsmobile.settings_ui.toga.InfoDialog') as notice:
                    info.on_press()
                    app.loop.run_until_complete(asyncio.sleep(0))
                    dialog.assert_awaited_once()
                    self.assertEqual(notice.call_args.args[0], title)
                    self.assertTrue(notice.call_args.args[1])
                    self.assertIs(dialog.await_args.args[0], notice.return_value)
                self.assertEqual(switch.value, previous)
            self.assertEqual(box.children[-2].text, 'About')
            self.assertIs(box.children[-1], app.build_version_label)
            self.assertIn('0.1.5', app.build_version_label.text)
            self.assertIsNotNone(app.build_version_label.style.color)
            from logisticsmobile.preferences import Preferences
            for control, key, value, saved in (
                    (app.restore_choice, 'restore_last_document', False, 'false'),
                    (app.clear_documents_choice, 'clear_unmodified_documents_on_restart', False, 'false'),
                    (app.font_choice, 'font_size', '23', '23')):
                control.value = value
                self.assertEqual(Preferences(app.private_root).values[key], saved)
            self.assertEqual(app.preferences.values['restore_last_document'], 'false')
            self.assertEqual(app.preferences.values['clear_unmodified_documents_on_restart'], 'false')

    def test_about_uses_packaged_identity_without_git(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'source.json'
            path.write_text(json.dumps(dict(logistics_commit='a' * 40,
                logistics_committed_at='2026-10-15T12:34:00+00:00', dirty=True,
                source_sha256='b' * 64)))
            with patch('logisticsmobile.settings_ui.installed_build') as git, \
                    patch('logisticsmobile.settings_ui.sys.platform', 'ios'):
                text = build_information('0.1.5', path)
            git.assert_not_called()
            self.assertIn('0.1.5 · aaaaaaaaaa', text)
            self.assertIn('2026-10-15', text)
            self.assertIn('modified', text)
            self.assertIn('Platform: iOS / iPadOS', text)
            self.assertIn('Source: bbbbbbbbbbbb', text)
