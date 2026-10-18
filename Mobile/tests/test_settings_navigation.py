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
        nav.buttons['Text & Markdown'].on_press()
        self.assertEqual(app.routes.screens['settings'][-1][0], 'settings-category')
        self.assertEqual(list(app.body.children), [nav.options['Text & Markdown']])
        self.assertIs(app.settings_status.parent, nav.sections['Text & Markdown'])
        app.font_choice.value = '24'
        self.assertEqual(Preferences(app.private_root).values['font_size'], '24')
        app.routes.back()
        self.assertEqual(list(app.body.children), [nav])
        nav.buttons['Folder Hub'].on_press()
        self.assertEqual(list(app.body.children), [nav.options['Folder Hub']])
        self.assertIs(app.show_legacy_choice.parent.parent, nav.sections['Folder Hub'])
        self.assertEqual(app.font_choice.value, '24')

    def test_tablet_switches_categories_in_place_with_one_selected_row(self):
        app, nav = self.app, self.nav
        self.width.return_value = 900
        app.resize_workspace()
        self.assertTrue(nav.wide)
        self.assertEqual(list(nav.children), [nav.sidebar, nav.detail])
        self.assertEqual(list(nav.detail.children), [nav.options['App']])
        nav.buttons['Read aloud'].on_press()
        self.assertFalse(app.routes.screens['settings'])
        self.assertEqual(list(nav.detail.children), [nav.options['Read aloud']])
        self.assertEqual(nav.buttons['Read aloud'].style.font_weight, 'bold')
        self.assertEqual(nav.buttons['App'].style.font_weight, 'normal')
        self.assertIs(app.settings_status.parent, nav.sections['Read aloud'])

    def test_rotation_preserves_selected_options_and_control_values(self):
        app, nav = self.app, self.nav
        nav.choose('Text & Markdown')
        app.font_choice.value = '25'
        font = app.font_choice
        self.width.return_value = 900
        app.resize_workspace()
        self.assertFalse(app.routes.screens['settings'])
        self.assertEqual(list(app.body.children), [nav])
        self.assertEqual(list(nav.detail.children), [nav.options['Text & Markdown']])
        self.width.return_value = 390
        app.resize_workspace()
        self.assertEqual(app.routes.screens['settings'][-1][0], 'settings-category')
        self.assertEqual(list(app.body.children), [nav.options['Text & Markdown']])
        app.routes.back()
        self.assertEqual(list(app.body.children), [nav])
        nav.choose('Text & Markdown')
        self.assertIs(app.font_choice, font)
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
        app, nav = self.app, self.nav
        self.width.return_value = 600
        with patch('logisticsmobile.fold_layout.seam_fraction', return_value=.46):
            nav.reflow()
            self.assertTrue(nav.wide)
            self.assertAlmostEqual(nav.sidebar.style.width, (nav.layout.content_width or 600) * .46)
        self.width.return_value = 780
        nav.reflow()
        self.assertTrue(nav.wide)
        self.assertEqual(list(nav.children), [nav.sidebar, nav.detail])

    def test_android_and_ios_have_categories_and_only_android_has_appearance(self):
        for backend, appearance in (('toga_android.app', True), ('toga_iOS.app', False)):
            with self.subTest(backend=backend), patch.object(type(self.app._impl), '__module__', backend):
                self.app.show_settings()
                nav = self.app.settings_navigation
                self.assertEqual('Appearance' in nav.sections, appearance)
                self.assertIn('Folder Hub', nav.sections)
                self.assertIn('About', nav.sections)
                for width in (900, 390):
                    self.width.return_value = width
                    nav.reflow()
                    nav.choose('Folder Hub')
                    self.assertEqual(nav.wide, width >= 640)
                    self.assertIs(self.app.show_legacy_choice.parent.parent, nav.sections['Folder Hub'])
