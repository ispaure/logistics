"""Native credential admission captures ZIP access and retires cancelled workers."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from contextlib import contextmanager
from io import BytesIO
from threading import Event
import unittest

from features.rclone.mobile.credential_loading import NativeCredentialLoad, run_credentials
from features.rclone.mobile.service import native_service
from commonUtils.runtime.operations import check_cancelled


class Package:
    data = b'encrypted zip fixture'
    names = {'Original': 'Alias'}

    @contextmanager
    def open(self, reference=None):
        with BytesIO(self.data) as stream:
            yield 'Fixture.zip', stream

    def aliases(self, reference=None):
        return self.names


class Client:
    generation = 1
    package_name = ''

    def __init__(self):
        self.loaded = []

    def import_package(self, access, reference, password, *, remember=True):
        with access.open(reference) as (name, stream):
            self.loaded.append((name, stream.read(), access.aliases(), password, remember))
        if password != 'correct':
            raise ValueError('Bad password')
        self.generation += 1
        self.package_name = name
        return ['Alias']

    def lock(self):
        self.generation += 1


class NativeCredentialTests(unittest.TestCase):
    def test_prepare_captures_zip_and_aliases_without_loading_and_unlock_is_once(self):
        client, package = Client(), Package()
        service = native_service(client).credentials
        prepared = service.prepare_load(NativeCredentialLoad(package, None, False), 'correct')
        package.data, package.names = b'replaced', {'Original': 'Other'}
        self.assertEqual(client.loaded, [])
        self.assertNotIn('correct', repr(prepared))
        result = service.unlock(prepared)
        self.assertEqual(result.remotes, ('Alias',))
        self.assertFalse(result.saved)
        self.assertEqual(result.generation, client.generation)
        self.assertEqual(client.loaded, [('Fixture.zip', b'encrypted zip fixture', {'Original': 'Alias'}, 'correct', False)])
        with self.assertRaises(ValueError):
            service.unlock(prepared)

    def test_external_generation_change_or_explicit_lock_cannot_unlock_a_stale_package(self):
        for explicit in (False, True):
            with self.subTest(explicit=explicit):
                client = Client()
                service = native_service(client).credentials
                prepared = service.prepare_load(NativeCredentialLoad(Package(), None), 'correct')
                if explicit:
                    service.lock()
                else:
                    client.generation += 1
                with self.assertRaises(ValueError):
                    service.unlock(prepared)
                self.assertEqual(client.loaded, [])

    def test_bad_password_preserves_generation_and_consumes_admission(self):
        client = Client()
        service = native_service(client).credentials
        prepared = service.prepare_load(NativeCredentialLoad(Package(), None), 'wrong')
        with self.assertRaises(ValueError):
            service.unlock(prepared)
        self.assertEqual(client.generation, 1)
        with self.assertRaises(ValueError):
            service.unlock(prepared)


class CredentialTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancellation_waits_for_publication_worker_and_prevents_late_commit(self):
        started, release, published = Event(), Event(), []
        def load(*args, context):
            started.set()
            if not release.wait(5):
                raise TimeoutError('Fixture was not released')
            check_cancelled(context.cancelled)
            published.append(True)
        task = asyncio.create_task(run_credentials(load))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            task.cancel()
            await asyncio.sleep(.02)
            self.assertFalse(task.done())
            task.cancel()
            await asyncio.sleep(.02)
            self.assertFalse(task.done())
        finally:
            release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(published, [])

    async def test_retired_host_refuses_publication(self):
        client = Client()
        service = native_service(client).credentials
        with self.assertRaises(ValueError):
            await run_credentials(service.load, NativeCredentialLoad(Package(), None), 'correct', valid=lambda: False)
        self.assertEqual(client.loaded, [])
