"""Real decoder and encrypted-provider Notes Library integration acceptance."""
from pathlib import Path
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from features.notes_library.ui.notes_library import NotesLibraryWindow

TEST_STAGE = TestStage.EXTENDED


class NotesLibraryIntegrationTests(QtTestCase):
    def wait_for_provider(self, window):
        # These workers run the real rclone transport, whose I/O budget is 30s.
        # Keep functional waits separate from the short in-process UI budget.
        self.wait_until(lambda: not window.progress.busy, timeout=30,
                        message=lambda: 'Encrypted provider did not finish: ' + window.progress.message.text())

    def open_library(self, root):
        (root / '.obsidian').mkdir(exist_ok=True)
        window = NotesLibraryWindow(lambda: LocalFiles(root), 'Parity')
        window.show()
        self.wait_until(lambda: not window.progress.busy)
        self.addCleanup(lambda: window.close() if __import__('shiboken6').isValid(window) else None)
        return window

    def test_inline_video_and_full_player_decode_and_release_transports(self):
        import shutil
        from PySide6.QtMultimedia import QMediaFormat
        with self.temporary_directory() as directory:
            root = Path(directory)
            source = '# Video\n\n![[potato.mp4]]\n\nFollowing text\n'
            (root / 'Home.md').write_text(source)
            (root / 'Media').mkdir()
            shutil.copyfile(Path(__file__).parents[1] / 'readers/fixtures/video/h264-aac.mp4', root / 'Media/potato.mp4')
            window = self.open_library(root)
            window.open_note('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            self.wait_until(lambda: bool(window.viewer.browser.inline_videos.cards))
            self.assertEqual(len(window.viewer.browser.inline_videos.cards), 1)
            card = next(iter(window.viewer.browser.inline_videos.cards.values()))
            self.assertTrue(card.play.isVisible())
            self.assertTrue(card.player.source().isEmpty())
            card.audio.setMuted(True)
            frames = []
            card.screen.videoSink().videoFrameChanged.connect(lambda frame: frames.append(frame.isValid()))
            card.play.click()
            self.assertFalse(card.player.source().isEmpty())
            if QMediaFormat().supportedFileFormats(QMediaFormat.ConversionMode.Decode):
                self.wait_until(lambda: any(frames) and card.player.position() > 0,
                                message='Embedded video did not decode a frame')
            self.assertIn('Following text', window.viewer.browser.toPlainText())
            window.viewer.set_editing(True)
            self.wait_until(lambda: bool(window.viewer.formatted_editor.inline_videos.cards))
            self.assertEqual(window.viewer.markdown_text(), source)
            media = window.library.image_source('Home.md')
            transports = [transport for _, transport in media.videos.values()]
            from features.video.ui.player import VideoWindow
            from commonUtils.runtime.resources.selection import ResourceChoice
            players = []
            def open_player(provider, path, parent):
                from features.video.ui.vlc_backend import VLCPlayback
                player = VideoWindow(ResourceChoice(provider, path),
                                     backend_factory=lambda owner: VLCPlayback(owner, interactive=False))
                player.player.native.audio_output_set('adummy')
                player.audio.setMuted(True)
                player.show()
                players.append(player)
                return player
            with patch('desktop.document_catalog.open_resource', side_effect=open_player):
                window.open_note('Media/potato.mp4')
            player = players[0]
            self.assertTrue(player.speed_button.isVisible())
            self.assertTrue(player.fullscreen_button.isVisible())
            self.assertEqual(player.choice.path, 'Media/potato.mp4')
            self.assertFalse(card.player.isPlaying())
            self.assertIs(window.document_stack.currentWidget(), window.viewer)
            self.wait_until(lambda: player.have_frame and player.player.position() > 0,
                            message='Full library video player did not decode a frame')
            transport = player.transport
            player.close()
            self.assertTrue(transport.closed.is_set())
            window.close()
            self.assertTrue(all(transport.closed.is_set() for transport in transports))

    def test_localcrypt_video_link_opens_full_player_with_original_provider(self):
        from io import BytesIO
        from features.rclone import executable
        from tests.local_crypt_fixture import crypt_fixture
        from logistics_build.build_retention import scratch
        if not executable.get_rclone_path().is_file():
            self.skipTest('Pinned rclone executable not installed')
        with scratch() as directory, crypt_fixture(directory, executable.get_rclone_path()) as fixture:
            provider = fixture.provider
            provider.mkdir('Media')
            movie = Path(__file__).parents[1] / 'readers/fixtures/video/h264-aac.mp4'
            provider.create_file('Media/Clip.mp4', BytesIO(movie.read_bytes()))
            provider.write_bytes('note.md', b'# Encrypted video\n\n![[Clip.mp4]]\n')
            window = NotesLibraryWindow(lambda: provider, 'Encrypted video')
            window.show()
            try:
                self.wait_for_provider(window)
                window.open_note('note.md')
                self.wait_for_provider(window)
                self.wait_until(lambda: bool(window.viewer.browser.inline_videos.cards))
                embedded = next(iter(window.viewer.browser.inline_videos.cards.values()))
                self.assertTrue(embedded.play.isVisible())
                with patch('desktop.document_catalog.open_resource') as opened:
                    window.open_note('Clip.mp4', resolve_link=True)
                    self.wait_for_provider(window)
                    opened.assert_called_once_with(provider, 'Media/Clip.mp4', window)
                self.assertEqual(window.history[window.index], 'note.md')
                self.assertFalse(embedded.player.isPlaying())
            finally:
                window.close()

    def test_real_localcrypt_and_crypt_remote_open_and_read_notes(self):
        from io import BytesIO
        from features.rclone import executable, session
        from features.rclone.remote_resources import RemoteResources
        from features.rclone.localcrypt.backend import CryptResources
        from tests.local_crypt_fixture import crypt_fixture
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone executable not installed')
        with self.temporary_directory() as directory, crypt_fixture(directory, binary) as fixture:
            fixture.provider.mkdir('.obsidian')
            fixture.provider.mkdir('Nested')
            fixture.provider.create_file('Nested/Next.md', BytesIO(b'# Nested note'))
            fixture.provider.create_file('Nested/Tech.md', BytesIO(b'# Tech'))
            from features.rclone.localcrypt.ui.views import CryptBrowserView
            with patch('features.rclone.executable.get_rclone_path', return_value=binary):
                view = CryptBrowserView(fixture.item)
            view.show()
            self.assertIsNone(view.notes_offer)
            self.wait_until(lambda: view.file_browser.views.root is not None)
            view.close()
            # Seed the synthetic cloud crypt with the same vault marker and nested note.
            environment, source, destination = session.launch(
                fixture.context, str(fixture.item.data), str(fixture.cloud))
            from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
            run_bytes([str(binary), '--config', session.NULL_CONFIG,
                       'copy', '--create-empty-src-dirs', source, destination], environment=environment, max_output=0)
            for remote in (False, True):
                with self.subTest(remote=remote):
                    factory = (lambda: RemoteResources(fixture.context, 'Secret', binary=binary)) if remote else (
                        lambda: CryptResources(fixture.item, binary=binary))
                    window = NotesLibraryWindow(factory, 'Encrypted fixture', remote=remote)
                    window.show()
                    self.wait_for_provider(window)
                    if remote:
                        self.assertIsNone(window.library)
                        self.assertIn('local copy', window.progress.message.text())
                        window.close()
                        continue
                    self.assertIsNotNone(window.library, window.progress.message.text())
                    self.assertEqual(window.viewer.allow_edit, not remote)
                    self.assertFalse(window.viewer.edit_button.isChecked())
                    self.assertIn('note.md', window.items)
                    window.open_note('note.md')
                    self.wait_for_provider(window)
                    self.assertIn('Original note', window.viewer.browser.toPlainText(), window.viewer.status.text())
                    window.viewer.set_editing(True)
                    self.assertEqual(len(window.storage.resources), 1)
                    url = window.viewer.browser.document().baseUrl().resolved(qt.QUrl('page.png'))
                    image = window.viewer.browser.document().resource(qt.QTextDocument.ResourceType.ImageResource, url)
                    self.assertFalse(image.isNull())
                    window.items['Nested'].setExpanded(True)
                    self.wait_for_provider(window)
                    window.open_note('Nested/Next.md')
                    self.wait_for_provider(window)
                    self.assertIn('Nested note', window.viewer.browser.toPlainText(), window.viewer.status.text())
                    window.viewer.follow_link(qt.QUrl('note.md'))
                    self.wait_for_provider(window)
                    self.assertEqual(window.storage.path, (window.provider.root / 'note.md').resolve(), window.viewer.status.text())
                    window.viewer.follow_link(qt.QUrl('Tech.md'))
                    self.wait_for_provider(window)
                    self.assertEqual(window.storage.path, (window.provider.root / 'Nested/Tech.md').resolve(), window.viewer.status.text())
                    window.back.click()
                    self.wait_for_provider(window)
                    self.assertEqual(window.history[window.index], 'note.md')
                    window.forward.click()
                    self.wait_for_provider(window)
                    self.assertEqual(window.history[window.index], 'Nested/Tech.md')
                    window.open_note('Nested/Next.md')
                    self.wait_for_provider(window)
                    if not remote:
                        for mode in ('formatted', 'source'):
                            window.viewer.set_edit_mode(mode)
                            window.viewer.active_editor().insertPlainText('Edited ' + mode + '. ')
                            window.viewer.save_document()
                            self.wait_for_provider(window)
                            self.assertFalse(window.viewer.is_modified, window.viewer.status.text())
                            self.assertIn(('Edited ' + mode).encode(), fixture.provider.read_bytes('Nested/Next.md'))
                    from shiboken6 import isValid
                    provider = window.provider
                    session.forget(provider.context)
                    self.wait_until(lambda: not isValid(window) or window.locked)
                    self.assertEqual(window.storage.data, b'')
                    self.assertTrue(provider.closed)
                    if isValid(window):
                        window.close()
