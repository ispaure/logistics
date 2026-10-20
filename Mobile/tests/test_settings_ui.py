"""Settings help preserves preference values; About uses the installed payload."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from logisticsmobile.app import LogisticsMobile
from logisticsmobile.settings_ui import build_information


class SettingsUITests(unittest.TestCase):
    def make_app(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        LogisticsMobile.storage_root = Path(directory.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(app.loop.close)
        self.addCleanup(app.main_window.close)
        return app

    def test_settings_menu_fits_before_mounting_and_reuses_sizing_until_resize(self):
        from logisticsmobile.settings_ui import fit_section
        app = self.make_app()
        menu_parents = []
        def fit(section, width):
            nav = app.settings_navigation
            if section is nav.sidebar.content:
                menu_parents.append(nav.parent)
            return fit_section(section, width)
        with patch.object(app.adaptive, 'content_width', return_value=390) as width, \
                patch('logisticsmobile.settings_ui.fit_section', side_effect=fit):
            app.show_settings()
            nav = app.settings_navigation
            self.assertEqual(menu_parents, [None])
            app.select_destination('home')
            app.select_destination('settings')
            nav.reflow()
            self.assertEqual(menu_parents, [None])
            width.return_value = 360
            nav.reflow()
            self.assertEqual(len(menu_parents), 2)
            self.assertIs(app.settings_navigation, nav)

    def test_phone_menu_defers_categories_and_about_and_reuses_existing_pages(self):
        from logisticsmobile.preferences import Preferences
        app = self.make_app()
        with patch.object(app.adaptive, 'content_width', return_value=390), \
                patch('logisticsmobile.settings_ui.build_information', return_value='Fixture build') as about:
            app.show_settings()
            nav = app.settings_navigation
            self.assertEqual(nav.sections.built, {})
            self.assertIn('About', nav.sections)
            self.assertEqual(nav.sections.built, {})
            nav.reflow()
            about.assert_not_called()
            app.show_settings()
            self.assertIs(app.settings_navigation, nav)
            nav.choose('Text')
            font = app.text_font_size_choice
            font.value = '23'
            self.assertFalse(hasattr(app, 'restore_choice'))
            saved = Preferences(app.private_root).values
            self.assertEqual(saved['text_font_size'], '23')
            self.assertEqual(saved['restore_last_document'], 'true')
            nav.choose('About')
            about.assert_called_once()
            nav.choose('Text')
            self.assertIs(app.text_font_size_choice, font)
            nav.choose('About')
            about.assert_called_once()
            self.assertEqual(set(nav.sections.built), {'Text', 'About'})
            app.reload_preferences()
            self.assertIsNot(app.settings_navigation, nav)
            self.assertFalse(hasattr(app, 'text_font_size_choice'))
            app.settings_navigation.choose('Text')
            self.assertEqual(app.text_font_size_choice.value, '23')

    def test_apple_fitting_reuses_measurement_label_and_skips_unchanged_text(self):
        import toga
        from logisticsmobile.settings_ui import fit_text
        label = toga.Label('A preference label that can wrap')
        label._impl.native = SimpleNamespace(font=SimpleNamespace(lineHeight=22))
        ruler = SimpleNamespace(text='', font=None)
        ruler.sizeThatFits = lambda size: SimpleNamespace(width=len(ruler.text) * 8)
        factory = Mock()
        factory.return_value.new.return_value = ruler
        objc = SimpleNamespace(ObjCClass=factory, CGSize=lambda width, height: (width, height))
        with patch.object(type(label._impl), '__module__', 'toga_iOS.widgets.label'), \
                patch.dict('sys.modules', {'rubicon.objc': objc}):
            fit_text(label, 100)
            factory.assert_called_once_with('UILabel')
            first = label.text
            fit_text(label, 100)
            self.assertEqual(label.text, first)
            fit_text(label, 200)
            factory.assert_called_once()
            self.assertLess(len(label.text.splitlines()), len(first.splitlines()))

    def test_restore_settings_do_not_refresh_unrelated_document_lists(self):
        app = self.make_app()
        with patch.object(app.adaptive, 'content_width', return_value=390):
            app.show_settings()
            app.settings_navigation.choose('App')
            with patch.object(app, 'refresh_document_overview') as documents:
                app.restore_choice.value = False
                app.clear_documents_choice.value = False
                documents.assert_not_called()
            self.assertEqual(app.preferences.values['restore_last_document'], 'false')
            self.assertEqual(app.preferences.values['clear_unmodified_documents_on_restart'], 'false')

    def test_help_order_dialog_and_about_at_bottom(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile', version='0.1.5')
            app.show_settings()
            app.settings_navigation.sections['App']
            app.settings_navigation.sections['Text']
            box = app.settings_navigation.sections['About']
            for switch, title in ((app.restore_choice, 'Restore last document'),
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
            self.assertEqual(list(app.settings_navigation.sections)[-1], 'About')
            self.assertEqual(box.children[0].text, 'About')
            self.assertIs(box.children[-1], app.build_version_label)
            self.assertIn('0.1.5', app.build_version_label.text)
            self.assertIsNotNone(app.build_version_label.style.color)
            from logisticsmobile.preferences import Preferences
            for control, key, value, saved in (
                    (app.restore_choice, 'restore_last_document', False, 'false'),
                    (app.clear_documents_choice, 'clear_unmodified_documents_on_restart', False, 'false'),
                    (app.text_font_size_choice, 'text_font_size', '23', '23')):
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
