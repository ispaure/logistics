"""Acquired provider readers retain cleanup ownership until view admission."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from mobile.provider_opening import ProviderDocumentOpening
from mobile.provider_view import ProviderView


class ProviderOpeningTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, *, remote=False):
        reader = NS(editable=True, read_only=False, kind='.md', name='Note.md', source=Mock())
        copies = NS(remote_storage=remote, open=Mock(return_value=reader))
        owner = NS(cloud_busy=False, crypt_password=NS(value=''), _crypt_cancel=None,
                   private_dirty=Mock(return_value=False), set_cloud_busy=Mock(),
                   private_comic_mode=Mock(return_value='single'),
                   format_services=NS(comic_sharing=Mock(return_value=False)),
                   private_comic_seam=Mock(return_value=0),
                   main_window=NS(size=NS(width=400, height=800), dialog=AsyncMock()),
                   provider_page_content=Mock(return_value=('text', '# Note')),
                   preferences=NS(values={'markdown_font_size': 16}),
                   current=NS(private=False), crypt_reader=None, show_view=Mock(return_value=True),
                   clear_private_reader=Mock(), crypt_title=NS(text=''), cloud_status=NS(value=''),
                   toggle_private_preview=Mock(), show_private_markdown_editor=Mock(),
                   screen_privacy=NS(refresh=Mock()), watch_provider_layout=Mock(),
                   watch_provider_epub_width=Mock())
        operation = ProviderDocumentOpening(owner)
        view = ProviderView()
        view.crypt_view, view.crypt_reader = object(), reader
        view.crypt_text, view.crypt_image = Mock(), Mock()
        operation.view.build = Mock(return_value=view)
        return operation, owner, reader, copies

    async def test_preview_failure_keeps_source_fallback_and_publishes_before_watching(self):
        operation, owner, reader, copies = self.fixture(remote=True)
        order = []
        owner.clear_private_reader.side_effect = lambda **kwargs: order.append('clear')
        owner.watch_provider_layout.side_effect = lambda: order.append(('layout', owner.crypt_reader))
        owner.watch_provider_epub_width.side_effect = lambda: order.append(('width', owner.crypt_reader))
        with patch('mobile.loading_progress.opening_options', return_value={}), \
                patch('mobile.preview.reader_image_source', return_value=None), \
                patch('mobile.preview.markdown_preview', side_effect=ValueError('Synthetic preview failure')):
            self.assertTrue(await operation.open(copies=copies, key='note'))
        self.assertEqual(order, ['clear', ('layout', reader), ('width', reader)])
        self.assertIn('Synthetic preview failure', owner.crypt_title.text)
        owner.toggle_private_preview.assert_not_called()
        owner.screen_privacy.refresh.assert_called_once()
        reader.source.close.assert_not_called()
        owner.crypt_text.dispose.assert_not_called()
        owner.crypt_image.dispose.assert_not_called()
        self.assertIsNone(owner._crypt_cancel)
        self.assertEqual(owner.set_cloud_busy.call_args_list, [unittest.mock.call(True), unittest.mock.call(False)])

    async def test_cancelled_preview_closes_acquired_remote_reader_before_publication(self):
        operation, owner, reader, copies = self.fixture(remote=True)
        def preview(*args, **kwargs):
            owner._crypt_cancel.set()
            return '<p>Late result</p>'
        with patch('mobile.loading_progress.opening_options', return_value={}), \
                patch('mobile.preview.reader_image_source', return_value=None), \
                patch('mobile.preview.markdown_preview', side_effect=preview):
            self.assertFalse(await operation.open(copies=copies, key='note'))
        operation.view.build.assert_not_called()
        owner.show_view.assert_not_called()
        owner.clear_private_reader.assert_not_called()
        owner.main_window.dialog.assert_not_awaited()
        reader.source.close.assert_called_once()
        self.assertIn('cancelled', owner.cloud_status.value)
        self.assertIsNone(owner._crypt_cancel)
        owner.set_cloud_busy.assert_called_with(False)

    async def test_view_veto_closes_only_newly_acquired_remote_readers(self):
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                operation, owner, reader, copies = self.fixture(remote=True)
                owner.show_view.return_value = False
                supplied = (reader, 'text', '# Note') if prepared else None
                with patch('mobile.loading_progress.opening_options', return_value={}):
                    self.assertFalse(await operation.open(copies=copies, key='note', prepared=supplied, edit=True))
                if prepared:
                    copies.open.assert_not_called()
                    reader.source.close.assert_not_called()
                else:
                    copies.open.assert_called_once()
                    reader.source.close.assert_called_once()
                owner.clear_private_reader.assert_not_called()
                view = operation.view.build.return_value
                view.crypt_text.dispose.assert_called_once()
                view.crypt_image.dispose.assert_called_once()
                owner.watch_provider_layout.assert_not_called()
                self.assertIsNone(owner._crypt_cancel)
                owner.set_cloud_busy.assert_called_with(False)

    async def test_page_preparation_failure_still_closes_the_acquired_remote_reader(self):
        operation, owner, reader, copies = self.fixture(remote=True)
        owner.provider_page_content.side_effect = OSError('Synthetic page failure')
        with patch('mobile.loading_progress.opening_options', return_value={}):
            await operation.open(copies=copies, key='note')
        reader.source.close.assert_called_once()
        operation.view.build.assert_not_called()
        owner.clear_private_reader.assert_not_called()
        owner.main_window.dialog.assert_awaited_once()
        self.assertIn('Synthetic page failure', owner.cloud_status.value)
        self.assertIsNone(owner._crypt_cancel)
        owner.set_cloud_busy.assert_called_with(False)

    async def test_neighbor_failure_after_adoption_keeps_session_controls_and_reader_owned(self):
        operation, owner, reader, copies = self.fixture(remote=True)
        reader.kind, reader.editable = '.cbz', False
        owner.refresh_provider_comic_neighbors = AsyncMock(side_effect=ValueError('Synthetic neighbor failure'))
        with patch('mobile.loading_progress.opening_options', return_value={}):
            await operation.open(copies=copies, key='comic')
        self.assertIs(owner.crypt_reader, reader)
        owner.crypt_text.dispose.assert_not_called()
        owner.crypt_image.dispose.assert_not_called()
        reader.source.close.assert_not_called()
        owner.main_window.dialog.assert_awaited_once()
        self.assertIn('Synthetic neighbor failure', owner.cloud_status.value)

    async def test_failed_build_preserves_current_reader_and_releases_only_acquired_source(self):
        operation, owner, reader, copies = self.fixture(remote=True)
        previous = owner.crypt_reader = NS(source=Mock())
        operation.view.build.side_effect = ValueError('Synthetic build failure')
        with patch('mobile.loading_progress.opening_options', return_value={}):
            await operation.open(copies=copies, key='note', edit=True)
        self.assertIs(owner.crypt_reader, previous)
        previous.source.close.assert_not_called()
        reader.source.close.assert_called_once()
        owner.clear_private_reader.assert_not_called()
        owner.show_view.assert_not_called()
        owner.watch_provider_layout.assert_not_called()
