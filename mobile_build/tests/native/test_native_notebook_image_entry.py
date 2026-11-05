"""Required native-image entry contracts, tested without starting an app."""
import asyncio
import importlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
PACKAGE = '_native_image_entry_fixture'


def load_entry():
    directory = Path(__file__).resolve().parents[3] / 'mobile_build/native_tests/tests/logisticsmobile'
    spec = importlib.util.spec_from_file_location(PACKAGE, directory / '__init__.py',
                                                 submodule_search_locations=[str(directory)])
    package = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = package
    spec.loader.exec_module(package)
    return SimpleNamespace(entry=importlib.import_module(PACKAGE + '.__main__'),
        images=importlib.import_module(PACKAGE + '.notebook_image_checks'),
        localcrypt=importlib.import_module(PACKAGE + '.localcrypt_checks'))


def successful_report():
    return dict(success=True, providers=[dict(provider=name, reopened=True, password_reprompt=True)
                                        for name in ('Local', 'LocalCrypt')])


async def successful_workflow(app):
    app._notebook_image_report = successful_report()
    return app._notebook_image_report


class NativeNotebookImageEntryTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_entry()

    @classmethod
    def tearDownClass(cls):
        for name in tuple(sys.modules):
            if name == PACKAGE or name.startswith(PACKAGE + '.'):
                sys.modules.pop(name, None)

    async def test_both_provider_success_is_required(self):
        app = SimpleNamespace()
        with patch.object(self.fixture.images, 'exercise_notebook_images', successful_workflow, create=True):
            result = await self.fixture.entry.required_notebook_images(app)
        self.assertIs(result, app._notebook_image_report)
        self.assertTrue(result['success'])

    async def test_primary_error_identity_and_partial_provider_evidence_survive(self):
        app, primary = SimpleNamespace(), ValueError('original workflow failure')
        async def failing(app):
            app._notebook_image_report = dict(success=False,
                providers=[dict(provider='Local', cases=['partial'])])
            raise primary
        with patch.object(self.fixture.images, 'exercise_notebook_images', failing, create=True):
            with self.assertRaises(ValueError) as caught:
                await self.fixture.entry.required_notebook_images(app)
        self.assertIs(caught.exception, primary)
        self.assertEqual(app._notebook_image_report['providers'][0]['cases'], ['partial'])
        self.assertFalse(app._notebook_image_report['success'])

    async def test_single_provider_cannot_report_success(self):
        app = SimpleNamespace()
        async def incomplete(app):
            app._notebook_image_report = successful_report()
            app._notebook_image_report['providers'].pop()
            return app._notebook_image_report
        with patch.object(self.fixture.images, 'exercise_notebook_images', incomplete, create=True):
            with self.assertRaises(AssertionError):
                await self.fixture.entry.required_notebook_images(app)
        self.assertFalse(app._notebook_image_report['success'])

    async def test_timeout_preserves_cleanup_and_inflight_evidence(self):
        app, actual_wait = SimpleNamespace(), asyncio.wait_for
        async def bounded(awaitable, timeout):
            self.assertEqual(timeout, 120)
            return await actual_wait(awaitable, .01)
        async def stalled(app):
            app._notebook_image_report = dict(success=False,
                providers=[dict(provider='LocalCrypt', cases=['in flight'])])
            try:
                await asyncio.Event().wait()
            finally:
                app._notebook_image_report['cleanup_attempted'] = True
        with patch.object(self.fixture.images, 'exercise_notebook_images', stalled, create=True), \
                patch.object(self.fixture.entry.asyncio, 'wait_for', bounded):
            with self.assertRaises(TimeoutError):
                await self.fixture.entry.required_notebook_images(app)
        self.assertTrue(app._notebook_image_report['cleanup_attempted'])
        self.assertEqual(app._notebook_image_report['providers'][0]['cases'], ['in flight'])

    async def test_image_marker_follows_localcrypt_management_return(self):
        async def localcrypt(app, passed, *, notebook_images=None):
            self.assertIsNotNone(notebook_images)
            await notebook_images()
            passed.append('native_localcrypt_file_management')
        passed = []
        with patch.object(self.fixture.images, 'exercise_notebook_images', successful_workflow, create=True), \
                patch.object(self.fixture.localcrypt, 'exercise_localcrypt', localcrypt):
            await self.fixture.entry.localcrypt_with_required_images(SimpleNamespace(), passed)
        self.assertEqual(passed, ['native_localcrypt_file_management', 'native_notebook_images'])

    async def test_missing_hook_fails_without_image_marker(self):
        async def localcrypt(app, passed, *, notebook_images=None):
            passed.append('native_localcrypt_file_management')
        passed = []
        with patch.object(self.fixture.localcrypt, 'exercise_localcrypt', localcrypt):
            with self.assertRaises(AssertionError):
                await self.fixture.entry.localcrypt_with_required_images(SimpleNamespace(), passed)
        self.assertNotIn('native_notebook_images', passed)

    async def test_duplicate_hook_fails_before_second_workflow(self):
        calls = []
        async def workflow(app):
            calls.append('images')
            return await successful_workflow(app)
        async def localcrypt(app, passed, *, notebook_images=None):
            await notebook_images()
            await notebook_images()
        passed = []
        with patch.object(self.fixture.images, 'exercise_notebook_images', workflow, create=True), \
                patch.object(self.fixture.localcrypt, 'exercise_localcrypt', localcrypt):
            with self.assertRaises(AssertionError):
                await self.fixture.entry.localcrypt_with_required_images(SimpleNamespace(), passed)
        self.assertEqual(calls, ['images'])
        self.assertNotIn('native_notebook_images', passed)

    async def test_clear_cloud_failure_prevents_image_marker_and_preserves_error(self):
        primary = ValueError('clear_cloud original failure')
        async def localcrypt(app, passed, *, notebook_images=None):
            await notebook_images()
            raise primary
        passed = []
        with patch.object(self.fixture.images, 'exercise_notebook_images', successful_workflow, create=True), \
                patch.object(self.fixture.localcrypt, 'exercise_localcrypt', localcrypt):
            with self.assertRaises(ValueError) as caught:
                await self.fixture.entry.localcrypt_with_required_images(SimpleNamespace(), passed)
        self.assertIs(caught.exception, primary)
        self.assertNotIn('native_notebook_images', passed)
