"""Real decoder and encrypted-provider Notes Library integration acceptance."""
from contextlib import contextmanager
import faulthandler
import json
from pathlib import Path
import sys
from threading import get_ident
from time import monotonic
import unittest
from unittest.mock import patch

from shiboken6 import isValid

from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from features.notes_library.ui.notes_library import NotesLibraryWindow

TEST_STAGE = TestStage.EXTENDED


def _capture_note_open(window, trace):
    """Snapshot the original admission failure before cancellation/cleanup alters it."""
    try:
        progress = window.progress
        operation = progress.operation
        thread = operation.thread if operation is not None else None
        valid = thread is not None and isValid(thread)
        delivered, delivered_error = progress._result
        state = dict(trace, captured_at=monotonic(), pending_kind=window.pending[0],
            busy=progress.busy, cancelled=progress.cancelled.is_set(), progress=progress.message.text(),
            operation_id=id(operation) if operation is not None else None, operation_valid=valid,
            delivered_result_type=type(delivered).__name__, delivered_error=delivered_error)
        if valid:
            state.update(running=operation.isRunning(), finished=operation.isFinished(),
                interruption_requested=thread.isInterruptionRequested(),
                worker_result_type=type(operation.result).__name__, worker_error=operation.error)
        print('NOTES_OPEN_DEADLINE ' + json.dumps(state, sort_keys=True), file=sys.stderr, flush=True)
    finally:
        # Do not retain live Python frames, or wait until teardown has cancelled
        # the worker. This synchronous dump includes every Python thread.
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)


@contextmanager
def _note_open_diagnostics(window):
    progress = window.progress
    original_start = progress.start
    trace = dict(requested_at=monotonic(), worker_entered_at=None, worker_returned_at=None,
                 worker_thread_id=None, worker_result_type_at_return=None,
                 last_worker_stage=None, last_worker_stage_at=None)

    def start(work, **options):
        def traced_work(report, cancelled):
            trace.update(worker_entered_at=monotonic(), worker_thread_id=get_ident())
            try:
                value = work(report, cancelled)
                trace['worker_result_type_at_return'] = type(value).__name__
                return value
            finally:
                trace['worker_returned_at'] = monotonic()
        return original_start(traced_work, **options)

    def stage(done, total, message):
        # Direct delivery records worker progress even if GUI delivery is late.
        # This observer stores primitives only and never accesses Qt widgets.
        trace.update(last_worker_stage=message, last_worker_stage_at=monotonic())

    progress.progress_changed.connect(stage, qt.Qt.ConnectionType.DirectConnection)
    try:
        with patch.object(progress, 'start', side_effect=start):
            try:
                yield
            except AssertionError:
                try:
                    _capture_note_open(window, trace)
                except Exception as error:
                    try:
                        print('NOTES_OPEN_DIAGNOSTIC_FAILED ' + type(error).__name__,
                              file=sys.stderr, flush=True)
                    except Exception:
                        pass  # A broken diagnostic stream must not replace the assertion.
                raise
    finally:
        try:
            progress.progress_changed.disconnect(stage)
        except Exception:
            pass  # Diagnostic observer retirement must not mask the test outcome.


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
            source = ('# Video\n\n' + 'Before the video.\n\n' * 80
                      + '![[potato.mp4]]\n\nFollowing text\n' + '\nMore text.\n' * 40)
            (root / 'Home.md').write_text(source)
            (root / 'Media').mkdir()
            shutil.copyfile(Path(__file__).parents[1] / 'readers/fixtures/video/h264-aac.mp4', root / 'Media/potato.mp4')
            window = self.open_library(root)
            with _note_open_diagnostics(window):
                window.open_note('Home.md')
                self.wait_until(lambda: not window.progress.busy)
            self.wait_until(lambda: bool(window.viewer.browser.inline_videos.cards))
            self.assertEqual(len(window.viewer.browser.inline_videos.cards), 1)
            card = next(iter(window.viewer.browser.inline_videos.cards.values()))
            self.assertTrue(card.play.isVisible())
            self.assertIsNone(card.player)
            browser = window.viewer.browser
            browser.setFocus()
            scrollbar = browser.verticalScrollBar()
            scrollbar.setValue(scrollbar.value() + card.y())
            self.wait_until(lambda: browser.viewport().rect().contains(card.geometry()))
            scroll_position = scrollbar.value()
            self.assertGreater(scroll_position, 0)
            create = card.create_player
            def muted_player():
                create()
                card.audio.setMuted(True)
            with patch.object(card, 'create_player', side_effect=muted_player):
                from PySide6.QtTest import QTest
                QTest.mouseClick(card.play, qt.Qt.MouseButton.LeftButton)
                self.wait_until(lambda: card.player is not None and not card.player.source().isEmpty())
            self.assertEqual(scrollbar.value(), scroll_position)
            if QMediaFormat().supportedFileFormats(QMediaFormat.ConversionMode.Decode):
                self.wait_until(lambda: not card.screen.current_image.isNull() and card.player.position() > 0,
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
            placeholders = ''.join(f'![[Synthetic-{index}.mp4]]\n\n' for index in range(12))
            provider.write_bytes('note.md', ('# Encrypted video\n\n' + placeholders + '![[Clip.mp4]]\n').encode())
            window = NotesLibraryWindow(lambda: provider, 'Encrypted video')
            window.show()
            try:
                self.wait_for_provider(window)
                with patch.object(window.library, 'link', wraps=window.library.link) as lookup:
                    window.open_note('note.md')
                    self.wait_for_provider(window)
                    self.wait_until(lambda: len(window.viewer.browser.inline_videos.cards) == 13)
                    cards = window.viewer.browser.inline_videos.cards.values()
                    self.assertTrue(all(card.player is None for card in cards))
                    self.assertFalse(window.library.image_source('note.md').videos)
                    lookup.assert_not_called()
                    embedded = next(card for card in cards if card.label == 'Clip.mp4')
                    create = embedded.create_player
                    def muted_player():
                        create()
                        embedded.audio.setMuted(True)
                    with patch.object(embedded, 'create_player', side_effect=muted_player):
                        embedded.play.click()
                        self.wait_until(lambda: embedded.player is not None and not embedded.player.source().isEmpty(),
                                        timeout=20)
                    lookup.assert_called_once()
                    self.assertEqual(lookup.call_args.args, ('note.md', 'Clip.mp4'))
                    self.assertEqual(list(window.library.image_source('note.md').videos), ['Media/Clip.mp4'])
                with patch('desktop.document_catalog.open_resource') as opened:
                    window.open_note('Clip.mp4', resolve_link=True)
                    self.wait_for_provider(window)
                    opened.assert_called_once_with(provider, 'Media/Clip.mp4', window)
                self.assertEqual(window.history[window.index], 'note.md')
                self.assertFalse(embedded.player.isPlaying())
            finally:
                window.close()

    def test_localcrypt_preview_batches_fallback_images_into_one_recursive_listing(self):
        from io import BytesIO
        from features.notes_library.notes import NotesLibrary
        from features.notes_library.preparation import prepare_document
        from tests.local_crypt_fixture import crypt_fixture, require_pinned_rclone
        from logistics_build.build_retention import scratch

        with scratch() as directory, crypt_fixture(directory, require_pinned_rclone(), pull=False) as fixture:
            provider = fixture.provider
            provider.mkdir('Vault')
            provider.mkdir('Vault/Attachments')
            provider.mkdir('Vault/.Hidden')
            for filename in ('first.png', 'second.png', 'third.png'):
                provider.create_file('Vault/Attachments/' + filename, BytesIO(fixture.image))
            provider.create_file('Vault/.Hidden/second.png', BytesIO(fixture.image))
            library = NotesLibrary(provider, 'Vault')
            self.addCleanup(library.close)
            provider.create_file('Vault/Preview.md', BytesIO(
                b'![[first.png]]\n\n![[second.png]]\n\n![[third.png]]'))
            with patch.object(provider, 'search_entries', wraps=provider.search_entries) as recursive, \
                    patch.object(provider, 'find_note_paths', wraps=provider.find_note_paths) as individual, \
                    patch.object(provider, 'indexed_list', side_effect=AssertionError('Unexpected per-folder listing')):
                prepared = prepare_document(library, 'Vault/Preview.md')
                try:
                    recursive.assert_called_once()
                    individual.assert_not_called()
                    self.assertEqual(len(prepared.resources), 3)
                    self.assertFalse(prepared.resources.errors)
                finally:
                    prepared.close()

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


class NotesOpenDiagnosticsTests(unittest.TestCase):
    def window(self):
        from threading import Event
        from types import SimpleNamespace
        class Signal:
            def __init__(self):
                self.callbacks = []
            def connect(self, callback, *args):
                self.callbacks.append(callback)
            def disconnect(self, callback):
                self.callbacks.remove(callback)
            def emit(self, *args):
                for callback in tuple(self.callbacks):
                    callback(*args)
        operation = SimpleNamespace(result=None, error=None, isRunning=lambda: False,
            isFinished=lambda: True, thread=SimpleNamespace(isInterruptionRequested=lambda: False))
        progress = SimpleNamespace(operation=operation, busy=True, cancelled=Event(),
            message=SimpleNamespace(text=lambda: 'Preparing embedded media…'),
            progress_changed=Signal(), _result=(None, ''))
        def start(work, **options):
            operation.result = work(lambda *args: None, progress.cancelled.is_set)
        progress.start = start
        return SimpleNamespace(progress=progress, pending=('note', 'Home.md', True, '', None))

    def test_capture_precedes_cleanup_and_preserves_original_failure_and_worker_state(self):
        from io import StringIO
        window = self.window()
        original_start = window.progress.start
        failure = AssertionError('original note-open deadline')
        events, output = [], StringIO()
        @contextmanager
        def cleanup():
            try:
                yield
            finally:
                events.append('cleanup')
                window.progress.cancelled.set()
        def work(report, cancelled):
            window.progress.progress_changed.emit(0, 0, 'Preparing embedded media…')
            return object()
        with patch(__name__ + '.isValid', return_value=True), patch.object(sys, 'stderr', output), \
                patch.object(faulthandler, 'dump_traceback', side_effect=lambda **kwargs: events.append('dump')) as dump:
            with self.assertRaises(AssertionError) as caught:
                with cleanup(), _note_open_diagnostics(window):
                    window.progress.start(work, message='Reading Home.md…')
                    raise failure
        self.assertIs(caught.exception, failure)
        self.assertEqual(events, ['dump', 'cleanup'])
        dump.assert_called_once_with(file=output, all_threads=True)
        state = json.loads(output.getvalue().removeprefix('NOTES_OPEN_DEADLINE '))
        self.assertEqual(state['operation_id'], id(window.progress.operation))
        self.assertEqual(state['worker_thread_id'], get_ident())
        self.assertLessEqual(state['worker_entered_at'], state['worker_returned_at'])
        self.assertEqual(state['last_worker_stage'], 'Preparing embedded media…')
        self.assertEqual(state['worker_result_type'], 'object')
        self.assertEqual(state['delivered_result_type'], 'NoneType')
        self.assertTrue(state['busy'])
        self.assertFalse(state['cancelled'])
        self.assertFalse(state['running'])
        self.assertTrue(state['finished'])
        self.assertIs(window.progress.start, original_start)
        self.assertEqual(window.progress.progress_changed.callbacks, [])

    def test_broken_capture_or_diagnostic_stream_cannot_replace_the_assertion(self):
        from io import StringIO
        class BrokenStream:
            def write(self, value):
                raise OSError('closed diagnostic stream')
            def flush(self):
                raise OSError('closed diagnostic stream')
        for output in (StringIO(), BrokenStream()):
            with self.subTest(broken_stream=isinstance(output, BrokenStream)):
                window = self.window()
                failure = AssertionError('preserve this failure')
                with patch(__name__ + '._capture_note_open', side_effect=RuntimeError('capture failed')), \
                        patch.object(sys, 'stderr', output):
                    with self.assertRaises(AssertionError) as caught:
                        with _note_open_diagnostics(window):
                            raise failure
                self.assertIs(caught.exception, failure)
                self.assertEqual(window.progress.progress_changed.callbacks, [])

    def test_success_does_not_capture_or_change_the_work_result(self):
        window = self.window()
        value = object()
        with patch(__name__ + '._capture_note_open') as capture:
            with _note_open_diagnostics(window):
                window.progress.start(lambda report, cancelled: value)
        capture.assert_not_called()
        self.assertIs(window.progress.operation.result, value)
        self.assertEqual(window.progress.progress_changed.callbacks, [])
