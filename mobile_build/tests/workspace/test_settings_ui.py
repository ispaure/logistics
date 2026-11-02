"""Settings explanations stay visible; About uses the installed payload."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mobile.app import LogisticsMobile
from mobile.settings.information import build_information


class SettingsUITests(unittest.TestCase):
    def test_about_license_navigation_search_and_native_back(self):
        import toga
        from services.open_source import Notice
        app = self.make_app()
        notice = Notice('Example', '1.0', 'MIT', '', 'Copyright Example')
        with patch('mobile.settings.licenses.installed_notices', return_value=[notice]):
            app.show_settings(present=False)
            app.settings_navigation.choose('About')
            def descendants(widget):
                yield widget
                if isinstance(widget, toga.ScrollContainer) and widget.content is not None:
                    yield from descendants(widget.content)
                for child in getattr(widget, 'children', ()):
                    yield from descendants(child)
            about = app.settings_navigation.sections['About']
            entry = next(widget for widget in descendants(about)
                         if isinstance(widget, toga.Button) and widget.text == 'Open-source licenses')
            entry.on_press()
            view = app.routes.screens['settings'][-1][1]
            search = next(widget for widget in descendants(view) if isinstance(widget, toga.TextInput))
            search.value = 'missing'
            self.assertTrue(any(getattr(widget, 'text', '') == 'No matching components.' for widget in descendants(view)))
            search.value = 'example'
            component = next(widget for widget in descendants(view)
                             if isinstance(widget, toga.Button) and widget.text == 'Example 1.0')
            component.on_press()
            detail = app.routes.screens['settings'][-1][1]
            text = next(widget for widget in descendants(detail) if isinstance(widget, toga.MultilineTextInput))
            self.assertTrue(text.readonly)
            self.assertIn('Copyright Example', text.value)
            app.routes.back()
            self.assertIs(app.routes.screens['settings'][-1][1], view)

    def test_privacy_updates_preserve_split_pane_text_width(self):
        import toga
        app = self.make_app()
        with patch.object(app.adaptive, 'content_width', return_value=900):
            app.show_settings(present=False)
            nav = app.settings_navigation
            nav.choose('Privacy & Security')
            section = nav.sections['Privacy & Security']

            def descendants(widget):
                yield widget
                for child in getattr(widget, 'children', ()):
                    yield from descendants(child)

            refresh = next(widget for widget in descendants(section) if isinstance(widget, toga.Button)
                           and widget.text == 'Refresh output and approvals')
            initial_width = refresh._settings_available_width
            self.assertLess(initial_width, 900)
            refresh.on_press()
            self.assertEqual(refresh._settings_available_width, initial_width)
            wifi = next(widget for widget in descendants(section) if isinstance(widget, toga.Switch)
                        and widget is not app.session_speech_choice)
            for enabled in (True, False, True):
                wifi.value = enabled
                self.assertEqual(refresh._settings_available_width, initial_width)

    def test_dynamic_privacy_rows_keep_one_arrow_and_inline_remove_controls(self):
        import toga
        from mobile.settings.forms import fit_section
        from mobile.settings.trusted_wifi import controls
        from commonUtils.ui.native import forms
        app = self.make_app()
        container = toga.Box()
        choice, manage = controls(app, container)
        with patch.object(forms, 'disclosure', wraps=forms.disclosure) as draw:
            for enabled in (True, False, True, False, True):
                choice.value = enabled
            self.assertEqual(draw.call_count, 1)
        self.assertTrue(manage._settings_disclosure)

        from services.audio_output import output
        device = output('test', 'settings-headset', 'A long Bluetooth headset name', bluetooth=True)
        app.audio_output.save({device.identity: device.label})
        app.show_settings(present=False)
        section = app.settings_navigation.sections['Privacy & Security']

        def descendants(widget):
            yield widget
            for child in getattr(widget, 'children', ()):
                yield from descendants(child)

        refresh = next(widget for widget in descendants(section) if isinstance(widget, toga.Button)
                       and widget.text == 'Refresh output and approvals')
        for _ in range(2):
            row = next(widget for widget in descendants(section)
                       if getattr(widget, '_settings_action_row', False))
            label, remove = row.children
            self.assertIsInstance(label, toga.Label)
            self.assertIsInstance(remove, toga.Button)
            self.assertEqual(remove.text, 'Remove')
            fit_section(section, 320)
            self.assertLess(label._settings_available_width, 220)
            self.assertFalse(getattr(remove, '_settings_disclosure', False))
            refresh.on_press()
        remove = next(widget for widget in descendants(section) if isinstance(widget, toga.Button)
                      and widget.text == 'Remove')
        remove.on_press()
        self.assertEqual(app.audio_output.approved(), {})
        self.assertFalse(any(getattr(widget, '_settings_action_row', False)
                             for widget in descendants(section)))

    def test_privacy_and_history_placement_and_explicit_page_arrows(self):
        import toga
        app = self.make_app()
        app.preferences.save(session_trusted_wifi='true')
        app.show_settings(present=False)
        sections = app.settings_navigation.sections

        def descendants(widget):
            yield widget
            for child in getattr(widget, 'children', ()):
                yield from descendants(child)

        def buttons(title):
            return {widget.text: widget for widget in descendants(sections[title])
                    if isinstance(widget, toga.Button)}

        expected = {
            'Privacy & Security': {
                'Trusted Wi-Fi networks…': True, 'Approve current output…': False,
            },
            'Workspaces': {
                'Migrate protected reader history…': False,
                'rclone connections…': True, 'SMB shares…': True,
            },
            'Reset': {
                'Clear all saved positions…': False, 'Clear all recent files…': False,
                'Erase all app data…': True,
            },
            'Help': {'Mobile documentation': True},
        }
        for title, actions in expected.items():
            actual = buttons(title)
            for label, opens_page in actions.items():
                with self.subTest(category=title, label=label):
                    self.assertEqual(bool(getattr(actual[label], '_settings_disclosure', False)), opens_page)
        self.assertNotIn('Migrate protected reader history…', buttons('App'))
        self.assertNotIn('Trusted Wi-Fi networks…', buttons('Workspaces'))
        self.assertIn(app.show_legacy_choice, list(descendants(sections['Workspaces'])))
        self.assertIn(app.session_speech_choice, list(descendants(sections['Privacy & Security'])))
        self.assertNotIn(app.session_speech_choice, list(descendants(sections['Read aloud'])))
        self.assertNotIn('Audio playback', sections)
        from commonUtils.ui.native.password_input import PasswordInput
        password = next(widget for widget in descendants(sections['Workspaces'])
                        if isinstance(widget, PasswordInput))
        from mobile.settings.forms import fit_section
        fit_section(sections['Workspaces'], 320)
        self.assertEqual(list(password.children), [password.field, password.eye])
        self.assertEqual(password.eye.style.height, 48)
        password.value = 'synthetic previous password'
        password.eye.on_press()
        self.assertTrue(password.revealed)
        self.assertEqual(password.value, 'synthetic previous password')

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
        from mobile.settings.forms import fit_section
        app = self.make_app()
        menu_parents = []
        def fit(section, width):
            nav = app.settings_navigation
            if section is nav._menu:
                if not menu_parents:
                    self.assertIsNone(nav.sidebar.content)
                menu_parents.append(nav.parent)
            return fit_section(section, width)
        with patch.object(app.adaptive, 'content_width', return_value=390) as width, \
                patch('mobile.settings.navigation.fit_section', side_effect=fit):
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

    def test_wide_menu_defers_all_pages_and_paints_each_row_once(self):
        from collections import Counter
        from mobile import appearance
        app = self.make_app()
        paints = Counter()
        original = appearance._surface_painter.paint
        def paint(impl, style):
            if appearance._surface_painter.pending.get() is None:
                paints[impl] += 1
            return original(impl, style)
        with patch.object(app.adaptive, 'content_width', return_value=900), \
                patch.object(appearance._surface_painter, 'paint', side_effect=paint):
            app.show_settings(present=False)
        nav = app.settings_navigation
        self.assertEqual(nav.sections.built, {})
        self.assertEqual(nav.options.built, {})
        self.assertFalse(hasattr(app, 'restore_choice'))
        for button in nav.buttons.values():
            self.assertEqual(paints[button._impl], 1)
            self.assertEqual(button._impl._surface_roles, ('transparent', 'text', False))
            self.assertGreaterEqual(button.style.height, 52)
        nav.choose('Text')
        self.assertEqual(set(nav.sections.built), {'Text'})
        self.assertEqual(set(nav.options.built), {'Text'})
        self.assertFalse(hasattr(app, 'restore_choice'))

    def test_retained_category_skips_fitting_but_messages_and_resize_still_refit(self):
        from mobile.settings.forms import fit_section
        app = self.make_app()
        with patch.object(app.adaptive, 'content_width', return_value=390) as width:
            app.show_settings()
            nav = app.settings_navigation
            with patch('mobile.settings.navigation.fit_section', wraps=fit_section) as fit:
                nav.choose('App')
                self.assertGreater(fit.call_count, 0)
                fit.reset_mock()
                nav.choose('App')
                nav.reflow()
                fit.assert_not_called()
                app.settings_status.text = 'A new status message that must wrap within the available settings pane.'
                self.assertIn('\n', app.settings_status.text)
                fit.assert_not_called()
                width.return_value = 320
                nav.reflow()
                self.assertGreater(fit.call_count, 0)

    def test_phone_menu_defers_categories_and_about_and_reuses_existing_pages(self):
        from mobile.preferences import Preferences
        app = self.make_app()
        with patch.object(app.adaptive, 'content_width', return_value=390), \
                patch('mobile.settings.categories.build_information', return_value='Fixture build') as about:
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
        from mobile.settings.forms import fit_text
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
            # A repeat must not read font metrics across the native bridge.
            label._impl.native = None
            fit_text(label, 100)
            self.assertEqual(label.text, first)
            label._impl.native = SimpleNamespace(font=SimpleNamespace(lineHeight=22))
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

    def test_explanations_follow_options_and_about_stays_at_bottom(self):
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
                label, control = switch.parent.children
                self.assertEqual(label.text.replace('\n', ' '), title)
                self.assertIs(control, switch)
                row = switch.parent
                group = row.parent
                section = group.parent
                self.assertIs(section.children[section.children.index(group) + 1], row._settings_note)
                self.assertTrue(row._settings_note.text)
                self.assertEqual(row._settings_note.style.font_size, 13)
            self.assertEqual(list(app.settings_navigation.sections)[-1], 'About')
            self.assertEqual(box.children[0].text, 'About')
            self.assertIs(box.children[-1], app.build_version_label)
            self.assertIn('0.1.5', app.build_version_label.text)
            self.assertIsNotNone(app.build_version_label.style.color)
            from mobile.preferences import Preferences
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
            with patch('mobile.settings.information.installed_build') as git, \
                    patch('mobile.settings.information.sys.platform', 'ios'):
                text = build_information('0.1.5', path)
            git.assert_not_called()
            self.assertIn('0.1.5 · aaaaaaaaaa', text)
            self.assertIn('2026-10-15', text)
            self.assertIn('modified', text)
            self.assertIn('Platform: iOS / iPadOS', text)
            self.assertIn('Source: bbbbbbbbbbbb', text)

    def test_about_finds_build_manifest_at_mobile_package_root(self):
        with TemporaryDirectory() as directory:
            package = Path(directory) / 'mobile'
            settings = package / 'settings'
            settings.mkdir(parents=True)
            (package / 'source.json').write_text(json.dumps(dict(
                logistics_commit='c' * 40,
                logistics_committed_at='2026-10-24T12:34:00+00:00',
                dirty=True, source_sha256='d' * 64)))
            with patch('mobile.settings.information.__file__', str(settings / 'information.py')), \
                    patch('mobile.settings.information.installed_build') as fallback, \
                    patch('mobile.settings.information.sys.platform', 'android'):
                text = build_information('0.1.5')
            fallback.assert_not_called()
            self.assertIn('0.1.5 · cccccccccc', text)
            self.assertRegex(text, r'2026-10-24 \d{2}:\d{2}')
            self.assertIn('modified', text)
            self.assertIn('Platform: Android', text)
            self.assertIn('Source: dddddddddddd', text)
