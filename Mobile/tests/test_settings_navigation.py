"""Category navigation adapts without rebuilding preferences or losing native Back."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import toga
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.preferences import Preferences


class SettingsNavigationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        width = patch.object(self.app.adaptive, 'content_width', return_value=390)
        self.width = width.start()
        self.addCleanup(width.stop)
        self.app.show_settings()
        self.nav = self.app.settings_navigation

    def test_phone_category_list_pushes_options_and_native_back_returns_to_list(self):
        app, nav = self.app, self.nav
        self.assertEqual(list(nav.children), [nav.sidebar])
        self.assertFalse(app.routes.screens['settings'])
        nav.buttons['Text'].on_press()
        self.assertEqual(app.routes.screens['settings'][-1][0], 'settings-category')
        self.assertEqual(list(app.body.children), [nav.options['Text']])
        self.assertIs(app.settings_status.parent, nav.sections['Text'])
        app.text_font_size_choice.value = '24'
        self.assertEqual(Preferences(app.private_root).values['text_font_size'], '24')
        app.routes.back()
        self.assertEqual(list(app.body.children), [nav])
        nav.buttons['Workspaces'].on_press()
        self.assertEqual(list(app.body.children), [nav.options['Workspaces']])
        self.assertIs(app.show_legacy_choice.parent.parent.parent, nav.sections['Workspaces'])
        self.assertEqual(app.text_font_size_choice.value, '24')

    def test_repeated_rotation_from_category_list_does_not_open_default_options(self):
        app, nav = self.app, self.nav
        for width in (900, 390, 900, 390, 900, 390):
            self.width.return_value = width
            app.resize_workspace()
            self.assertFalse(app.routes.screens['settings'])
            self.assertIs(app.body.children[0], nav)
        self.assertFalse(nav.detail_requested)
        self.assertEqual(nav.sections.built, {})
        self.assertEqual(nav.options.built, {})

    def test_category_selected_wide_survives_rotation_while_another_tab_is_visible(self):
        app, nav = self.app, self.nav
        self.width.return_value = 900
        app.resize_workspace()
        nav.choose('Text')
        app.show_home()
        self.width.return_value = 390
        nav.reflow()
        app.native_host.activate('settings')
        nav.reflow()
        self.assertEqual(app.routes.screens['settings'][-1][0], 'settings-category')
        self.assertIs(app.body.children[0], nav.options['Text'])
        app.routes.back()
        self.assertFalse(nav.detail_requested)

    def test_tablet_switches_categories_in_place_with_one_selected_row(self):
        app, nav = self.app, self.nav
        self.width.return_value = 900
        app.resize_workspace()
        self.assertTrue(nav.wide)
        self.assertEqual(list(nav.children), [nav.sidebar, nav.detail])
        self.assertEqual(list(nav.detail.children), [])
        self.assertEqual(nav.sections.built, {})
        self.assertEqual(nav.options.built, {})
        nav.buttons['Read aloud'].on_press()
        self.assertFalse(app.routes.screens['settings'])
        self.assertEqual(list(nav.detail.children), [nav.options['Read aloud']])
        self.assertEqual(nav.buttons['Read aloud'].style.font_weight, 'bold')
        self.assertEqual(nav.buttons['App'].style.font_weight, 'normal')
        self.assertIs(app.settings_status.parent, nav.sections['Read aloud'])

    def test_rotation_preserves_selected_options_and_control_values(self):
        app, nav = self.app, self.nav
        nav.choose('Text')
        app.text_font_size_choice.value = '25'
        font = app.text_font_size_choice
        self.width.return_value = 900
        app.resize_workspace()
        self.assertFalse(app.routes.screens['settings'])
        self.assertEqual(list(app.body.children), [nav])
        self.assertEqual(list(nav.detail.children), [nav.options['Text']])
        self.width.return_value = 390
        app.resize_workspace()
        self.assertEqual(app.routes.screens['settings'][-1][0], 'settings-category')
        self.assertEqual(list(app.body.children), [nav.options['Text']])
        app.routes.back()
        self.assertEqual(list(app.body.children), [nav])
        nav.choose('Text')
        self.assertIs(app.text_font_size_choice, font)
        self.assertEqual(font.value, '25')

    def test_resizing_nested_page_preserves_it_then_back_restores_wide_category(self):
        app, nav = self.app, self.nav
        nav.choose('Books & Comics')
        nested = toga.Box()
        app.show_view(nested, destination='settings', route='settings-nested', title='Saved books')
        self.width.return_value = 900
        app.resize_workspace()
        self.assertIs(app.body.children[0], nested)
        self.assertEqual(len(app.routes.screens['settings']), 2)
        app.routes.back()
        self.assertFalse(app.routes.screens['settings'])
        self.assertEqual(list(app.body.children), [nav])
        self.assertEqual(list(nav.detail.children), [nav.options['Books & Comics']])

    def test_duo_landscape_seam_splits_the_panes_and_unfolded_width_keeps_them(self):
        nav = self.nav
        self.width.return_value = 600
        with patch('logisticsmobile.fold_layout.seam_fraction', return_value=.46):
            nav.reflow()
            self.assertTrue(nav.wide)
            self.assertAlmostEqual(nav.sidebar.style.width, (nav.layout.content_width or 600) * .46)
        self.width.return_value = 780
        nav.reflow()
        self.assertTrue(nav.wide)
        self.assertEqual(list(nav.children), [nav.sidebar, nav.detail])

    def test_android_and_ios_have_appearance_categories(self):
        for backend in ('toga_android.app', 'toga_iOS.app'):
            # Native toolbar mounting has separate platform fixtures; this checks categories.
            with self.subTest(backend=backend), patch.object(type(self.app._impl), '__module__', backend), \
                    patch('logisticsmobile.android_reader_chrome.sync'):
                self.app.show_settings(rebuild=True)
                nav = self.app.settings_navigation
                self.assertIn('Appearance', nav.sections)
                self.assertIn('Workspaces', nav.sections)
                self.assertIn('About', nav.sections)
                for width in (900, 390):
                    self.width.return_value = width
                    nav.reflow()
                    nav.choose('Workspaces')
                    self.assertEqual(nav.wide, width >= 640)
                    self.assertIs(self.app.show_legacy_choice.parent.parent.parent, nav.sections['Workspaces'])

    def test_narrow_crease_pane_wraps_all_categories_and_widening_restores_text(self):
        app, nav = self.app, self.nav
        self.width.return_value = 600
        with patch('logisticsmobile.fold_layout.seam_fraction', return_value=.55):
            nav.reflow()
            nav.choose('App')
            self.assertEqual(nav.sidebar.style.width, 330)
            label, switch = app.clear_documents_choice.parent.children
            self.assertEqual(label.text.replace('\n', ' '), 'Close saved documents on restart')
            self.assertGreater(len(label.text.splitlines()), 1)
            note = switch.parent._settings_note
            self.assertGreater(len(note.text.splitlines()), 1)
            self.assertEqual(note.text.replace('\n', ' '), note._settings_source_text)
            self.assertIs(switch, app.clear_documents_choice)
            nav.choose('LM Chat')
            button = nav.sections['LM Chat'].children[1].children[0]
            self.assertIn('\n', button.text)
            self.assertGreater(button.style.height, 48)
            nav.choose('Books & Comics')
            hint = next(child for child in nav.sections['Books & Comics'].children
                        if isinstance(child, toga.Label) and child.text.startswith('Keep'))
            original = hint._settings_source_text
            self.assertGreater(len(hint.text.splitlines()), len(original.splitlines()))
        self.width.return_value = 1400
        nav.reflow()
        self.assertEqual(hint.text, original)
        self.assertEqual(nav.selected, 'Books & Comics')
        # Hidden categories fit their new pane width when revisited.
        nav.choose('LM Chat')
        self.assertEqual(button.text, 'Server & generation settings…')
        self.assertEqual(button.style.height, 52)

    def test_changed_status_is_rewrapped_from_the_new_message(self):
        self.width.return_value = 600
        with patch('logisticsmobile.fold_layout.seam_fraction', return_value=.55):
            self.nav.reflow()
            self.nav.choose('App')
        self.app.settings_status.text = 'Preferences saved on this device.'
        self.assertIn('\n', self.app.settings_status.text)
        self.assertEqual(self.app.settings_status.text.replace('\n', ' '),
                         'Preferences saved on this device.')
        self.assertEqual(self.app.settings_status._settings_source_text,
                         'Preferences saved on this device.')
