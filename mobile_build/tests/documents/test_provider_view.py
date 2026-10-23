"""Failed provider construction retires its controls, preserving the active reader."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from features.text_editor.resources import TextReader
from mobile.app import LogisticsMobile
from mobile.provider_view import ProviderDocumentView, ProviderView


class ProviderViewTests(TestCase):
    def test_discard_is_idempotent_and_retires_other_controls_after_cleanup_failure(self):
        view = ProviderView()
        view.crypt_reader = Mock()
        view.crypt_text = Mock()
        view.crypt_text.dispose.side_effect = ValueError('Synthetic cleanup failure')
        view.crypt_image = Mock()
        with self.assertLogs('mobile.provider_view', level='ERROR'):
            view.discard()
        view.discard()
        view.crypt_text.dispose.assert_called_once()
        view.crypt_image.dispose.assert_called_once()
        view.crypt_reader.source.close.assert_not_called()
        with self.assertRaises(RuntimeError):
            view.adopt(Mock())

    def test_failure_after_content_construction_retires_unpublished_controls(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.show_cloud(present=False)
            previous = app.crypt_reader
            drafts = []
            def fail(view):
                drafts.append(view)
                raise ValueError('Synthetic chrome construction failure')
            reader = TextReader('Unpublished.txt', b'Discard these temporary controls')
            with patch.object(app, 'compact_private_view', side_effect=fail):
                with self.assertRaisesRegex(ValueError, 'Synthetic chrome'):
                    ProviderDocumentView(app).build(reader, object(), 'text', reader.text)
            self.assertEqual(len(drafts), 1)
            self.assertTrue(drafts[0].crypt_text.closed)
            self.assertIsNone(drafts[0].crypt_image.image)
            self.assertIs(app.crypt_reader, previous)
