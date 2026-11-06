"""Rotation selection visits its declared screens without unrelated setup."""
from contextlib import ExitStack
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from commonUtils.testing.stages import TestStage
from mobile_build.native_tests.tests.logisticsmobile import rotation_checks, rotation_screens

TEST_STAGE = TestStage.REGRESSION


class RotationInventoryTests(unittest.TestCase):
    def test_screen_ids_are_unique_and_groups_have_setup(self):
        screens = rotation_screens.SCREENS
        self.assertEqual(len({screen.panel for screen in screens}), len(screens))
        self.assertEqual({screen.group for screen in screens}, set(rotation_screens._SCENARIOS))

    def test_selection_uses_suite_order_and_preserves_report_ids(self):
        chosen = rotation_screens.select_screens({'provider-epub-find', 'home', 'workspace-Network shares'})
        self.assertEqual([s.panel for s in chosen], ['workspace-Network shares', 'home', 'provider-epub-find'])
        for panels in ([], {'typo'}, 'home'):
            with self.subTest(panels=panels), self.assertRaises(ValueError):
                rotation_screens.select_screens(panels)

    def test_source_navigation_and_settings_catalogs_expose_coverage_gaps(self):
        from mobile.navigation import DESTINATION_ITEMS
        from mobile.settings.categories import CATEGORIES
        inventory = rotation_screens.coverage_inventory(DESTINATION_ITEMS, CATEGORIES, panels={'settings-text'})
        self.assertEqual([r['panel'] for r in inventory['screens'] if r['selected']], ['settings-text'])
        covered = {r['title'] for r in inventory['screens']}
        missing = {r['title'] for r in inventory['gaps']}
        self.assertTrue({row[1] for row in DESTINATION_ITEMS} <= covered)
        self.assertEqual({'Settings → ' + c.title for c in CATEGORIES} - covered, missing)
        self.assertIn('Settings → Appearance', covered)
        self.assertIn('Settings → Camera', missing)
        self.assertTrue({title for _, title in rotation_screens.SETTINGS_SCREENS} <= {c.title for c in CATEGORIES})
        future = rotation_screens.coverage_inventory(
            (*DESTINATION_ITEMS, ('future', 'Future screen', '', '')), (*CATEGORIES, NS(title='New category')))
        self.assertTrue({'Future screen', 'Settings → New category'} <= {r['title'] for r in future['gaps']})

    def test_nested_documentation_state_is_not_hidden_by_retained_settings_category(self):
        page = object()
        app = NS(native_host=NS(state=NS(destination='settings')), body=NS(children=[page]),
                 settings_navigation=NS(detail_requested=True, selected='Text', sidebar=object()),
                 routes=NS(screens={'settings': [('documentation', page, None)]}),
                 adaptive=NS(detail_routes=(), in_detail=False),
                 documentation=NS(web=object(), path='first', history=['first'], history_index=0))
        original = rotation_checks.panel_state(app)
        for field, value in (('web', object()), ('path', 'second'), ('history', ['second']), ('history_index', 1)):
            with self.subTest(field=field), patch.object(app.documentation, field, value):
                self.assertNotEqual(rotation_checks.panel_state(app), original)


class RotationVisitTests(unittest.IsolatedAsyncioTestCase):
    async def test_focused_home_uses_no_fixture_or_unrelated_app_capabilities(self):
        app = NS(show_home=Mock())
        check = AsyncMock()
        with patch.object(rotation_screens._Fixtures, 'root', new_callable=Mock,
                          side_effect=AssertionError('unexpected fixture')):
            await rotation_screens.visit_screens(app, check, panels={'home'})
        app.show_home.assert_called_once_with()
        check.assert_awaited_once_with('home')

    async def test_nested_configuration_runs_its_parent_without_rotating_parent(self):
        app = NS(show_chat=Mock(), show_chat_configuration=Mock())
        check = AsyncMock()
        await rotation_screens.visit_screens(app, check, panels={'chat-configuration'})
        app.show_chat.assert_called_once_with()
        app.show_chat_configuration.assert_called_once_with()
        check.assert_awaited_once_with('chat-configuration')

    async def test_inventory_missing_repeated_or_extra_visits_fail(self):
        for names in ([], ['home', 'home'], ['unexpected']):
            async def scenario(app, fixtures, selected, check):
                for name in names:
                    await check(name)
            with self.subTest(names=names), patch.dict(rotation_screens._SCENARIOS, home=scenario):
                with self.assertRaises(AssertionError):
                    await rotation_screens.visit_screens(object(), AsyncMock(), panels={'home'})

    async def test_selection_and_cycle_errors_fail_before_mutating_app(self):
        for kwargs in (dict(panels=[]), dict(panels={'typo'}), dict(cycles=0), dict(cycles=-1), dict(cycles=True)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                await rotation_checks.exercise_rotation(object(), **kwargs)

    async def test_native_audit_keeps_full_orientation_sequence_and_records_coverage(self):
        app = NS(show_home=Mock())
        with ExitStack() as stack:
            stack.enter_context(patch.object(rotation_checks.asyncio, 'sleep', new_callable=AsyncMock))
            stack.enter_context(patch.object(rotation_checks, 'panel_state', return_value='same content'))
            rotate = stack.enter_context(patch.object(rotation_checks, 'rotate_panel', new_callable=AsyncMock))
            stack.enter_context(patch.object(rotation_checks, 'settled_rotation_layout', new_callable=AsyncMock, return_value=3))
            stack.enter_context(patch.object(rotation_checks, 'safe_geometry', return_value={'view_width': 320}))
            stack.enter_context(patch.object(rotation_checks, 'pose_snapshot', return_value={}))
            stack.enter_context(patch('builtins.print'))
            result = await rotation_checks.exercise_rotation(app, cycles=2, panels={'home'})
        expected = ['portrait', 'landscape-left', 'portrait', 'landscape-right', 'portrait'] * 2
        self.assertEqual([row['orientation'] for row in result['rotation_samples']], expected)
        self.assertEqual([call.kwargs['orientation'] for call in rotate.await_args_list], expected)
        self.assertEqual([row['cycle'] for row in result['rotation_samples']], [0] * 5 + [1] * 5)
        self.assertTrue(result['rotation_preserves_panels'])
        self.assertEqual([row['panel'] for row in result['rotation_inventory']['screens'] if row['selected']], ['home'])


class RotationScenarioTests(unittest.TestCase):
    def test_focused_settings_resets_retained_wide_category_before_root_audit(self):
        from mobile_build.tests.support.app import mobile_app
        with mobile_app() as app, patch.object(app.adaptive, 'content_width', return_value=900):
            app.show_settings()
            app.settings_navigation.choose('Text')
            self.assertTrue(app.settings_navigation.detail_requested)
            async def check(name):
                self.assertEqual(name, 'settings')
                self.assertFalse(app.settings_navigation.detail_requested)
                self.assertFalse(app.settings_navigation.detail.children)
            app.loop.run_until_complete(rotation_screens.visit_screens(app, check, panels={'settings'}))

    def test_refused_category_is_not_reported_as_visited(self):
        from mobile_build.tests.support.app import mobile_app
        with mobile_app() as app:
            app.show_settings()
            with patch.object(app.settings_navigation, 'choose', return_value=None):
                check = AsyncMock()
                with self.assertRaisesRegex(AssertionError, 'Settings category was refused'):
                    app.loop.run_until_complete(rotation_screens.visit_screens(app, check, panels={'settings-appearance'}))
                check.assert_not_awaited()

    def test_focused_folder_does_not_restore_previously_selected_remote(self):
        from mobile_build.tests.support.app import mobile_app
        from commonUtils.runtime.resources.local import LocalFiles
        with mobile_app() as app:
            app.folder_source = 'rclone'
            async def check(name):
                self.assertEqual(name, 'folder')
                self.assertIsInstance(app.file_provider, LocalFiles)
                self.assertTrue(any(row['name'] == 'Child' for row in app.file_rows.values()))
            with patch.object(app, 'start_cloud_restore') as restore:
                app.loop.run_until_complete(rotation_screens.visit_screens(app, check, panels={'folder'}))
            restore.assert_not_called()

    def test_full_sweep_visits_real_synthetic_screens_in_inventory_order(self):
        from mobile_build.tests.support.app import mobile_app
        from mobile_build.tests.support.readers import MemoryWebView
        seen = []
        with mobile_app() as app, ExitStack() as patches:
            # Dummy has no private browser; use a memory-only fixture
            # to exercise the native rich-reader setup, not its HTML renderer.
            patches.enter_context(patch('features.books.mobile.provider_reader.private_webview_supported', return_value=True))
            patches.enter_context(patch('features.books.mobile.provider_reader.PrivateWebView', MemoryWebView))
            patches.enter_context(patch('mobile_build.native_tests.tests.logisticsmobile.web_checks.wait_for_text', new_callable=AsyncMock))
            async def check(name):
                self.assertTrue(app.body.children, name)
                seen.append(name)
                if name == 'nested-folder':
                    self.assertTrue(any(row['name'] == 'Note.md' for row in app.file_rows.values()))
                elif name == 'settings-text':
                    self.assertEqual(app.settings_navigation.selected, 'Text')
                elif name == 'provider-epub-find':
                    self.assertIsNotNone(app.private_sessions.active.provider_epub_view)
            app.loop.run_until_complete(rotation_screens.visit_screens(app, check))
        self.assertEqual(seen, [screen.panel for screen in rotation_screens.SCREENS])
