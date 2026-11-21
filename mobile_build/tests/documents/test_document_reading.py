"""Reader session capabilities preserve privacy independently of encryption labels."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from commonUtils.runtime.resources.local import LocalFiles
from features.rclone.localcrypt.mobile.copies import LocalCryptCopies
from features.rclone.mobile.remote_readers import RemoteReaders
from services.documents.mobile_reading import (
    DocumentReadCapabilities, reading_capabilities, close_document_reader,
)
from services.documents.mobile_storage import TextDocumentCopies


class DocumentReadingTests(unittest.TestCase):
    def test_remote_declaration_alone_enforces_private_credential_bound_readonly_access(self):
        source = NS(document_capabilities=DocumentReadCapabilities(
            private=False, writable=True, credential_bound=False, offline=False, remote=True))
        self.assertEqual(reading_capabilities(source), DocumentReadCapabilities(
            private=True, writable=False, credential_bound=True, offline=False, remote=True))

    def test_private_session_does_not_imply_a_credential_dependency(self):
        source = NS(document_capabilities=DocumentReadCapabilities(
            private=True, writable=False, credential_bound=False, offline=True))
        self.assertTrue(reading_capabilities(source).private)
        self.assertFalse(reading_capabilities(source).credential_bound)

    def test_ordinary_text_remains_available_without_credentials(self):
        with TemporaryDirectory() as folder:
            copies = TextDocumentCopies(LocalFiles(Path(folder)))
            self.assertEqual(reading_capabilities(copies), DocumentReadCapabilities(
                private=False, writable=True, credential_bound=False, offline=True))

    def test_encryption_flag_cannot_determine_remote_lifetime_or_writes(self):
        source = NS(document_capabilities=RemoteReaders.document_capabilities,
                    encrypted=False, remote_storage=True)
        capabilities = reading_capabilities(source)
        self.assertTrue(capabilities.private)
        self.assertTrue(capabilities.credential_bound)
        self.assertTrue(capabilities.remote)
        self.assertFalse(capabilities.writable)
        self.assertFalse(capabilities.offline)

    def test_localcrypt_declares_offline_access_without_persistent_plaintext(self):
        source = NS(document_capabilities=LocalCryptCopies.document_capabilities)
        self.assertEqual(reading_capabilities(source), DocumentReadCapabilities(
            private=True, writable=True, credential_bound=True, offline=True, required_feature='rclone'))

    def test_adapter_declaration_cannot_hide_wrapped_remote_policy(self):
        with TemporaryDirectory() as folder:
            provider = LocalFiles(Path(folder))
            provider.remote_storage = True
            source = NS(provider=provider, document_capabilities=DocumentReadCapabilities(
                private=False, writable=True, credential_bound=False, offline=False))
            capabilities = reading_capabilities(source)
            self.assertTrue(capabilities.private)
            self.assertTrue(capabilities.credential_bound)
            self.assertFalse(capabilities.writable)
            self.assertTrue(capabilities.remote)

    def test_password_is_retired_even_when_source_close_fails(self):
        reader = NS(pdf=Mock(), source=NS(close=Mock(side_effect=OSError('close failed'))), password='secret')
        with self.assertRaisesRegex(OSError, 'close failed'):
            close_document_reader(reader)
        reader.pdf.close.assert_called_once_with()
        self.assertEqual(reader.password, '')

    def test_media_or_pdf_failure_cannot_skip_remaining_reader_cleanup(self):
        for failing in ('media', 'pdf'):
            with self.subTest(failing=failing):
                media, pdf, source = Mock(), Mock(), Mock()
                {'media': media, 'pdf': pdf}[failing].close.side_effect = OSError(failing + ' close failed')
                reader = NS(_markdown_media=media, pdf=pdf, source=source, password='synthetic-password')
                with self.assertRaisesRegex(OSError, failing + ' close failed'):
                    close_document_reader(reader)
                for resource in (media, pdf, source):
                    resource.close.assert_called_once_with()
                self.assertEqual(reader.password, '')


class ProviderWorkerLifetimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_pdf_page_render_borrow_survives_repeated_cancellation(self):
        import asyncio
        from threading import Event
        from mobile.provider_ui import ProviderUI
        from mobile.provider_document import ProviderDocumentSession
        release, started = Event(), asyncio.Event()
        loop = asyncio.get_running_loop()
        def blocking(*args):
            loop.call_soon_threadsafe(started.set)
            if not release.wait(5):
                raise RuntimeError('Fixture not released')
            return 'pdf', (b'', [])
        reader = NS(kind='.pdf', editable=False, labels=['one'], book=None,
                    source=NS(close=Mock()))
        owner = NS(active_host=True, cloud_busy=False, crypt_reader=reader,
                   workspace=NS(token=lambda key: ('doc', 0), accepts=lambda token: True),
                   session=NS(id='doc'), crypt_title=NS(text='Unchanged'),
                   crypt_read_page=NS(enabled=True), crypt_page=NS(value='one'),
                   crypt_content=NS(children=[]), private_comic_mode=lambda: 'single',
                   private_comic_seam=lambda: 0, format_services=NS(comic_sharing=lambda: False),
                   provider_page_content=blocking, move_private_page=Mock())
        owner.app = owner
        owner.manager = NS(active=owner, controllers={'doc': owner})
        owner.document_access = lambda: None
        owner.set_document_busy = owner.set_cloud_busy = lambda busy: setattr(owner, 'cloud_busy', busy)
        owner.workspace.sessions = {'doc': owner.session}
        document = owner._provider_document = ProviderDocumentSession(owner)
        document.reader = reader
        owner.provider_document = lambda: document
        task = asyncio.create_task(ProviderUI.read_crypt_page(owner))
        try:
            await asyncio.wait_for(started.wait(), 2)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            self.assertTrue(owner.cloud_busy)
            with self.assertRaises(OSError):
                document.dispose()
            reader.source.close.assert_not_called()
        finally:
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertFalse(owner.cloud_busy)
        self.assertEqual(owner.crypt_title.text, 'Unchanged')
        owner.move_private_page.assert_not_called()

    def save_owner(self, *, metadata=False):
        import asyncio
        from mobile.provider_ui import ProviderUI
        class Owner(ProviderUI):
            @property
            def cloud_busy(self):
                return self.provider_document().busy
            def set_cloud_busy(self, busy):
                self.provider_document().busy = busy
                (self.operation_idle.clear if busy else self.operation_idle.set)()
            set_document_busy = set_cloud_busy
        owner = Owner()
        owner.app, owner.active_host = owner, True
        owner.session = NS(id='doc')
        generation = [0]
        owner.workspace = NS(token=lambda key: ('doc', generation[0]),
                             accepts=lambda token: token == ('doc', generation[0]),
                             invalidate=lambda key: generation.__setitem__(0, generation[0] + 1),
                             sessions={'doc': owner.session})
        owner.manager = NS(controllers={'doc': owner}, active=owner, terminal=False)
        owner.document_access = lambda: None
        owner.operation_idle = asyncio.Event()
        owner.operation_idle.set()
        owner.crypt_reader = NS(kind='.cbz' if metadata else '.txt', editable=not metadata,
                                text='Original', name='synthetic', labels=['page'], book=None,
                                source=NS(close=Mock()), comic=NS(info=NS(get_field=lambda key: 'Saved')))
        owner.crypt_text = NS(value='Submitted', readonly=False)
        owner.crypt_title = NS(text='Unchanged')
        owner.crypt_save = NS(enabled=True)
        owner.crypt_metadata_save = NS(enabled=True)
        owner.crypt_metadata_status = NS(text='Unchanged')
        owner.crypt_metadata_initial = {'title': 'Original'}
        owner.crypt_metadata_fields = {'title': NS(value='Submitted', readonly=False)}
        owner.crypt_page = NS(items=['page'], value='page')
        owner._crypt_reader_store = NS()
        owner.private_comic_mode = lambda: 'single'
        owner.private_comic_seam = lambda: 0
        owner.format_services = NS(comic_sharing=lambda: False)
        owner.provider_page_content = Mock(return_value=('image', 'synthetic'))
        for name in ('_show_crypt_content', 'refresh_private_bookmarks', 'watch_provider_layout',
                     'watch_provider_epub_width', 'refresh_private_text_controls'):
            setattr(owner, name, Mock())
        return owner

    async def test_cancelled_save_actual_outcome_reconciles_live_stale_and_failed_owners(self):
        import asyncio
        from threading import Event
        from unittest.mock import patch
        for metadata in (False, True):
            for outcome in ('success', 'failed', 'stale', 'later-edit', 'close-reenters'):
                with self.subTest(metadata=metadata, outcome=outcome):
                    owner = self.save_owner(metadata=metadata)
                    document, original = owner.provider_document(), owner.crypt_reader
                    returned = NS(**vars(original))
                    returned.source = NS(close=Mock())
                    returned.text = 'Submitted'
                    returned.password = 'synthetic'
                    entered, release, finished = asyncio.Event(), Event(), Event()
                    loop = asyncio.get_running_loop()
                    def save(*args, **kwargs):
                        loop.call_soon_threadsafe(entered.set)
                        try:
                            if not release.wait(5):
                                raise RuntimeError('Fixture not released')
                            if outcome == 'failed':
                                raise ValueError('Synthetic save failed')
                            return returned
                        finally:
                            finished.set()
                    owner._crypt_reader_store.save = owner._crypt_reader_store.save_metadata = save
                    if outcome == 'close-reenters':
                        original.source.close.side_effect = lambda: owner.workspace.invalidate('doc')
                    with patch('services.documents.access.can_write', return_value=True), \
                            patch('features.comics.mobile.metadata.patch', return_value={'title': 'Submitted'}):
                        task = asyncio.create_task(owner.save_crypt_metadata() if metadata else owner.save_crypt())
                        try:
                            await asyncio.wait_for(entered.wait(), 2)
                            if outcome == 'stale':
                                owner.workspace.invalidate('doc')
                            elif outcome == 'later-edit':
                                owner.crypt_text.value = owner.crypt_metadata_fields['title'].value = 'Later draft'
                            task.cancel()
                            await asyncio.sleep(0)
                            task.cancel()
                            await asyncio.sleep(0)
                            self.assertTrue(owner.cloud_busy)
                            self.assertFalse(owner.operation_idle.is_set())
                            self.assertTrue(document.cancel.is_set())
                            with self.assertRaises(OSError):
                                document.reader = returned
                            original.source.close.assert_not_called()
                        finally:
                            release.set()
                            with self.assertRaises(asyncio.CancelledError):
                                await task
                            self.assertTrue(await asyncio.to_thread(finished.wait, 2))
                    self.assertFalse(owner.cloud_busy)
                    self.assertTrue(owner.operation_idle.is_set())
                    self.assertIsNone(document.cancel)
                    self.assertEqual(owner.crypt_title.text, 'Unchanged')
                    self.assertEqual(owner.crypt_metadata_status.text, 'Unchanged')
                    owner._show_crypt_content.assert_not_called()
                    if outcome in ('failed', 'stale'):
                        self.assertIs(owner.crypt_reader, original)
                        original.source.close.assert_not_called()
                        self.assertTrue(owner.private_dirty())
                        if outcome == 'stale':
                            returned.source.close.assert_called_once_with()
                            self.assertEqual(returned.password, '')
                    else:
                        self.assertIs(owner.crypt_reader, returned)
                        original.source.close.assert_called_once_with()
                        returned.source.close.assert_not_called()
                        if metadata and outcome != 'close-reenters':
                            self.assertEqual(owner.crypt_metadata_initial, {'title': 'Saved'})
                        if outcome == 'later-edit':
                            self.assertTrue(owner.private_dirty())
                            self.assertEqual(owner.crypt_metadata_fields['title'].value, 'Later draft')
                    if outcome in ('stale', 'close-reenters'):
                        self.assertFalse((owner.crypt_metadata_save if metadata else owner.crypt_save).enabled)
                    else:
                        self.assertTrue((owner.crypt_metadata_save if metadata else owner.crypt_save).enabled)
                        self.assertFalse(owner.crypt_text.readonly if not metadata else owner.crypt_metadata_fields['title'].readonly)

    async def test_metadata_refresh_is_a_second_borrow_after_committed_save(self):
        import asyncio
        from threading import Event
        from unittest.mock import patch
        owner = self.save_owner(metadata=True)
        returned = NS(**vars(owner.crypt_reader))
        returned.source = NS(close=Mock())
        owner._crypt_reader_store.save_metadata = lambda *args, **kwargs: returned
        entered, release = asyncio.Event(), Event()
        loop = asyncio.get_running_loop()
        def page(*args):
            loop.call_soon_threadsafe(entered.set)
            if not release.wait(5):
                raise RuntimeError('Fixture not released')
            return 'image', 'synthetic'
        owner.provider_page_content = page
        with patch('features.comics.mobile.metadata.patch', return_value={'title': 'Submitted'}):
            task = asyncio.create_task(owner.save_crypt_metadata())
            try:
                await asyncio.wait_for(entered.wait(), 2)
                self.assertIs(owner.crypt_reader, returned)
                self.assertEqual(owner.crypt_metadata_initial, {'title': 'Saved'})
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                self.assertFalse(task.done())
                self.assertTrue(owner.cloud_busy)
                with self.assertRaises(OSError):
                    owner.provider_document().dispose()
                returned.source.close.assert_not_called()
            finally:
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        owner._show_crypt_content.assert_not_called()
        self.assertFalse(owner.cloud_busy)

    async def test_stale_page_success_error_and_finally_do_not_publish_controls(self):
        from threading import Event
        import asyncio
        for fails in (False, True):
            with self.subTest(fails=fails):
                owner = self.save_owner(metadata=True)
                owner.crypt_read_page = NS(enabled=True)
                owner.crypt_content = NS(children=[])
                owner.private_comic_viewport = lambda: (100, 100)
                owner.manager.revoke_stale = Mock()
                entered, release = asyncio.Event(), Event()
                loop = asyncio.get_running_loop()
                def page(*args):
                    loop.call_soon_threadsafe(entered.set)
                    if not release.wait(5):
                        raise RuntimeError('Fixture not released')
                    if fails:
                        raise ValueError('Synthetic decoder failure')
                    return 'image', 'synthetic'
                owner.provider_page_content = page
                task = asyncio.create_task(owner.read_crypt_page())
                try:
                    await asyncio.wait_for(entered.wait(), 2)
                    owner.active_host = False
                finally:
                    release.set()
                    await task
                self.assertFalse(owner.cloud_busy)
                self.assertTrue(owner.operation_idle.is_set())
                self.assertFalse(owner.crypt_read_page.enabled)
                self.assertEqual(owner.crypt_title.text, 'Unchanged')
                owner._show_crypt_content.assert_not_called()
                owner.manager.revoke_stale.assert_not_called()
                owner.crypt_reader.source.close.assert_not_called()

    async def test_saved_reader_progress_borrow_reconciles_cancellation_and_terminal_retirement(self):
        import asyncio
        from threading import Event
        from unittest.mock import patch
        for metadata in (False, True):
            for outcome in ('cancelled', 'terminal', 'failed', 'same-reader-stale'):
                with self.subTest(metadata=metadata, outcome=outcome):
                    owner = self.save_owner(metadata=metadata)
                    document, original = owner.provider_document(), owner.crypt_reader
                    returned = original if outcome == 'same-reader-stale' else NS(**vars(original))
                    returned.key = 'synthetic'
                    if returned is not original:
                        returned.source = NS(close=Mock())
                    returned.password = 'synthetic-password'
                    owner._crypt_reader_store.save = owner._crypt_reader_store.save_metadata = Mock(return_value=returned)
                    entered, release = asyncio.Event(), Event()
                    loop = asyncio.get_running_loop()

                    def load():
                        loop.call_soon_threadsafe(entered.set)
                        if not release.wait(5):
                            raise RuntimeError('Fixture not released')
                        if outcome == 'failed':
                            raise OSError('Synthetic progress load failure')

                    replacement = NS(load=load, close=Mock(), worker=None, watch_surface=Mock())
                    previous = owner._provider_progress = NS(worker=None, sample_surface=Mock(),
                                                             close=Mock(), retire=Mock())
                    def replace(successor):
                        owner._provider_progress = successor
                        return successor
                    previous.replace_with = Mock(side_effect=replace)
                    with patch('services.documents.access.can_write', return_value=True), \
                            patch('features.comics.mobile.metadata.patch', return_value={'title': 'Submitted'}), \
                            patch('mobile.provider_progress.ProviderProgress', return_value=replacement):
                        task = asyncio.create_task(owner.save_crypt_metadata() if metadata else owner.save_crypt())
                        try:
                            await asyncio.wait_for(entered.wait(), 2)
                            if outcome == 'terminal':
                                document.terminal = True
                                returned.source.close.side_effect = [OSError('Retry close'), None]
                                replacement.close.side_effect = [OSError('Retry progress close'), None]
                            elif outcome == 'same-reader-stale':
                                owner.workspace.invalidate('doc')
                            if outcome in ('cancelled', 'terminal'):
                                task.cancel()
                                await asyncio.sleep(0)
                                task.cancel()
                                await asyncio.sleep(0)
                            self.assertFalse(task.done())
                            self.assertTrue(owner.cloud_busy)
                            self.assertFalse(owner.operation_idle.is_set())
                            self.assertIsNotNone(document.worker)
                            with self.assertRaises(OSError):
                                document.dispose()
                            with self.assertRaises(OSError):
                                document.reader = original
                            original.source.close.assert_not_called()
                            replacement.close.assert_not_called()
                        finally:
                            release.set()
                            if outcome in ('cancelled', 'terminal'):
                                with self.assertRaises(asyncio.CancelledError):
                                    await task
                            else:
                                await task
                    self.assertFalse(owner.cloud_busy)
                    self.assertTrue(owner.operation_idle.is_set())
                    self.assertIsNone(document.worker)
                    self.assertIsNone(document.cancel)
                    owner._show_crypt_content.assert_not_called()
                    if outcome == 'cancelled':
                        self.assertIs(document.reader, returned)
                        previous.replace_with.assert_called_once_with(replacement)
                        replacement.close.assert_not_called()
                        original.source.close.assert_called_once_with()
                        if metadata:
                            self.assertEqual(owner.crypt_metadata_initial, {'title': 'Saved'})
                    else:
                        self.assertIs(document.reader, original)
                        previous.replace_with.assert_not_called()
                        replacement.close.assert_called_once_with()
                        original.source.close.assert_not_called()
                        if returned is not original:
                            returned.source.close.assert_called_once_with()
                            self.assertEqual(returned.password, '')
                    if outcome == 'terminal':
                        document.dispose()
                        document.dispose()
                        self.assertTrue(document.closed)
                        self.assertIsNone(document.reader)
                        self.assertEqual(returned.source.close.call_count, 2)
                        self.assertEqual(replacement.close.call_count, 2)
                        original.source.close.assert_called_once_with()
                        self.assertEqual(owner.crypt_text.value, '')
                        self.assertEqual(owner.crypt_metadata_fields, {})

    async def test_speech_borrow_rejects_stale_reader_gate_and_cancelled_output(self):
        import asyncio
        from threading import Event
        for outcome in ('cancelled', 'cancelled-error', 'gate', 'terminal', 'intent', 'wrong-reader'):
            with self.subTest(outcome=outcome):
                owner = self.save_owner(metadata=True)
                document, reader = owner.provider_document(), owner.crypt_reader
                owner.privacy_gate = NS(revision=0)
                owner.provider_speech_read_allowed = lambda: True
                valid = [True]
                entered, release = asyncio.Event(), Event()
                loop = asyncio.get_running_loop()
                def page(*args):
                    loop.call_soon_threadsafe(entered.set)
                    if not release.wait(5):
                        raise RuntimeError('Fixture not released')
                    if outcome == 'cancelled-error':
                        raise OSError('Synthetic speech failure')
                    return 'epub', 'Private speech'
                owner.provider_page_content = Mock(side_effect=page)
                if outcome == 'wrong-reader':
                    with self.assertRaises(PermissionError):
                        await owner.read_provider_speech_chapter(NS(**vars(reader)), 0, lambda: True)
                    owner.provider_page_content.assert_not_called()
                    continue
                task = asyncio.create_task(owner.read_provider_speech_chapter(reader, 0, lambda: valid[0]))
                try:
                    await asyncio.wait_for(entered.wait(), 2)
                    if outcome.startswith('cancelled'):
                        task.cancel()
                        await asyncio.sleep(0)
                        task.cancel()
                        await asyncio.sleep(0)
                        self.assertTrue(document.cancel.is_set())
                    elif outcome == 'gate':
                        owner.privacy_gate.revision += 1
                    elif outcome == 'intent':
                        valid[0] = False
                    else:
                        document.terminal = True
                    self.assertFalse(task.done())
                    self.assertFalse(owner.operation_idle.is_set())
                    with self.assertRaises(OSError):
                        document.dispose()
                    reader.source.close.assert_not_called()
                finally:
                    release.set()
                    with self.assertRaises(asyncio.CancelledError if outcome.startswith('cancelled') else PermissionError):
                        await task
                self.assertFalse(owner.cloud_busy)
                self.assertTrue(owner.operation_idle.is_set())
                self.assertIsNone(document.worker)
                self.assertIsNone(document.cancel)
                self.assertEqual(owner.crypt_title.text, 'Unchanged')
                if outcome == 'terminal':
                    document.dispose()
                    reader.source.close.assert_called_once_with()

    async def test_control_failure_releases_reservation_without_borrowing_reader(self):
        from unittest.mock import patch
        owner = self.save_owner()
        class RetiredButton:
            @property
            def enabled(self):
                return False
            @enabled.setter
            def enabled(self, value):
                raise OSError('Synthetic retired control')
        owner.crypt_save = RetiredButton()
        with patch('services.documents.access.can_write', return_value=True):
            with self.assertRaisesRegex(OSError, 'retired control'):
                await owner.save_crypt()
        self.assertFalse(owner.cloud_busy)
        self.assertTrue(owner.operation_idle.is_set())
        self.assertIsNone(owner.provider_document().cancel)
        self.assertTrue(owner.provider_document().can_start())

    async def test_progress_error_after_adoption_preserves_the_published_owner(self):
        from unittest.mock import patch
        owner = self.save_owner()
        original = owner.crypt_reader
        returned = NS(**vars(original))
        returned.key, returned.source = 'synthetic', NS(close=Mock())
        owner._crypt_reader_store.save = Mock(return_value=returned)
        replacement = NS(load=Mock(), close=Mock(), worker=None)
        previous = owner._provider_progress = NS(worker=None, sample_surface=Mock())
        def replace(successor):
            owner._provider_progress = successor
            raise OSError('Synthetic progress error after adoption')
        previous.replace_with = replace
        with patch('services.documents.access.can_write', return_value=True), \
                patch('mobile.provider_progress.ProviderProgress', return_value=replacement):
            await owner.save_crypt()
        self.assertIs(owner.crypt_reader, returned)
        self.assertIs(owner._provider_progress, replacement)
        replacement.close.assert_not_called()
        returned.source.close.assert_not_called()
        original.source.close.assert_called_once_with()
        self.assertFalse(owner.cloud_busy)
        owner.provider_document().dispose()
        replacement.close.assert_called_once_with()
        returned.source.close.assert_called_once_with()
