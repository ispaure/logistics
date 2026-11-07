"""Remaining reader adapters through actual Qt reopening and a fresh process."""

from contextlib import closing, ExitStack
from dataclasses import asdict
from pathlib import Path
import json
import subprocess
import sys
from unittest.mock import patch

from commonUtils.testing.stages import TestStage, stage
from commonUtils.tests.qt_test_case import QtTestCase

TEST_STAGE = TestStage.REGRESSION


class FormatProgressTests(QtTestCase):
    def setUp(self):
        from commonUtils.ui import pyside as qt

        self.app = qt.QApplication.instance()
        self.root = Path(self.temporary_directory().name)
        self.cache = self.root / 'cache'
        self.enterContext(patch('commonUtils.filesystem.storage.cache_directory', return_value=self.cache))
        self.enterContext(patch('services.documents.ui.text_position.cache_directory', return_value=self.cache))

    def test_read_only_pdf_reopens_visible_page_and_clear_fences_stale_window(self):
        from pypdf import PdfWriter
        from features.pdf.ui.reader import open_pdf
        from services.documents.history_controls import clear_saved_positions

        path = self.root / 'paper.pdf'
        pdf = PdfWriter()
        for _ in range(4):
            pdf.add_blank_page(200, 300)
        pdf.write(path)
        path.chmod(0o444)
        first = open_pdf(path)
        first.show()
        first.go(2)
        first.close()
        second = open_pdf(path)
        second.show()
        self.app.processEvents()
        self.assertEqual(second.view.pageNavigator().currentPage(), 2)
        second.go(3)
        clear_saved_positions(self.cache)
        second.close()
        third = open_pdf(path)
        self.assertEqual(third.index, 0)
        third.close()

    def test_markdown_reopens_preview_scroll_without_saving_text(self):
        from services.documents.ui.markdown import ProgressMarkdownWindow

        path = self.root / 'notes.md'
        path.write_text('# Private fixture marker\n\n' + '\n\n'.join(f'Paragraph {i}.' for i in range(200)))
        first = ProgressMarkdownWindow(path)
        first.show()
        self.app.processEvents()
        bar = first.viewer.browser.verticalScrollBar()
        self.assertGreater(bar.maximum(), 100)
        bar.setValue(bar.maximum() // 2)
        first.close()
        second = ProgressMarkdownWindow(path)
        second.show()
        self.app.processEvents()
        bar = second.viewer.browser.verticalScrollBar()
        self.assertAlmostEqual(bar.value() / bar.maximum(), .5, delta=.02)
        second.close()
        state = b''.join(file.read_bytes() for file in (self.cache / 'ReaderPositions').rglob('*.json'))
        self.assertTrue(state)
        self.assertNotIn(b'Private fixture marker', state)
        self.assertNotIn(b'Paragraph 100.', state)

    def test_notebook_fresh_process_restores_brush_colors_and_stable_page_id_after_reordering(self):
        from features.notebooks.editor import Editor
        from features.notebooks.notebook import Notebook
        from features.notebooks.progress import notebook_progress_state, open_notebook_progress, restore_notebook_progress
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.storage import DocumentResource

        path = self.root / 'notes.rmdoc'
        book = Notebook.new('Reading fixture')
        book.add_page()
        book.add_page()
        path.write_bytes(book.to_bytes())
        with DocumentResource(LocalFiles(self.root), path.name, max_bytes=2**20) as resource:
            progress, saved = open_notebook_progress(book, self.cache, resource=resource)
            self.assertEqual(saved, {})
            editor = Editor(book, lambda _: self.fail('Navigation checkpointed ink.'))
            restore_notebook_progress(editor, saved)
            editor.apply(dict(op='page', index=2))
            chosen = book.pages[editor.index].id
            editor.brush_colors = {15: 6, 18: -1}
            progress.save(notebook_progress_state(editor))
            progress.retire()
        book.move_page(2, 1)
        path.write_bytes(book.to_bytes())
        output = subprocess.check_output([sys.executable, '-c', """
from pathlib import Path
import json, sys
from features.notebooks.editor import Editor
from features.notebooks.notebook import Notebook
from features.notebooks.progress import open_notebook_progress, restore_notebook_progress
from commonUtils.runtime.resources.local import LocalFiles
from services.documents.storage import DocumentResource
path, root = map(Path, sys.argv[1:])
with DocumentResource(LocalFiles(path.parent), path.name, max_bytes=2**20) as resource:
    book = Notebook.read(resource.read())
    _, saved = open_notebook_progress(book, root, resource=resource)
    editor = Editor(book)
    restore_notebook_progress(editor, saved)
    print(json.dumps([editor.index, book.pages[editor.index].id, editor.brush_colors]))
""", str(path), str(self.cache)], text=True)
        self.assertEqual(json.loads(output), [1, chosen, {'15': 6, '18': -1}])

    @stage(TestStage.EXTENDED)
    def test_localcrypt_notebook_reopens_brush_colors_from_encrypted_progress(self):
        from io import BytesIO
        from features.notebooks.editor import Editor
        from features.notebooks.notebook import Notebook
        from features.notebooks.progress import notebook_progress_state, open_notebook_progress, restore_notebook_progress
        from services.documents.progress import ProgressMode, ProgressStatus
        from services.documents.storage import DocumentResource
        from tests.local_crypt_fixture import crypt_fixture, require_pinned_rclone

        name = 'private-sketch.rmdoc'
        original = Notebook.new('Private sketch').to_bytes()
        with (crypt_fixture(self.root, require_pinned_rclone(), state_password='synthetic-package-password', pull=False) as fixture,
              ExitStack() as browser):
            browser.callback(fixture.provider.acquire())
            fixture.provider.create_file(name, BytesIO(original))
            for writing in (True, False):
                with DocumentResource(fixture.provider, name, max_bytes=2**20) as resource:
                    self.assertEqual(resource.read(), original)
                    editor = Editor(Notebook.read(original))
                    progress, saved = open_notebook_progress(editor.notebook, self.cache, resource=resource)
                    self.assertIs(progress.mode, ProgressMode.ENCRYPTED)
                    restore_notebook_progress(editor, saved)
                    if writing:
                        editor.brush_colors = {15: 6, 18: -1}
                        self.assertIs(progress.save(notebook_progress_state(editor)), ProgressStatus.SAVED)
                    else:
                        self.assertEqual(editor.brush_colors, {15: 6, 18: -1})
                    progress.retire()
            directory = self.cache / 'ReaderPositions'
            archive, = directory.glob('*.zip')
            self.assertNotIn(b'brush_colors', archive.read_bytes())
            self.assertFalse(list(directory.rglob('*.json')))

    def test_video_fingerprint_migration_and_track_settings_after_process_restart(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from features.video.playback import VideoContent
        from features.video.session import PlaybackSettings
        from services.documents.video_progress import VideoProgress
        from services.documents.video_settings import SettingsStore, VideoSettingsStore

        video_root = self.cache / 'Video'
        video_root.mkdir(parents=True)
        path = self.root / 'renamed.mp4'
        path.write_bytes(b'video fixture' * 1000)
        settings = PlaybackSettings(audio_track=4, audio_track_key='stream-fr-commentary', subtitle_track=-1,
                                    audio_delay_ms=-250, subtitle_delay_ms=330, subtitle_scale=1.75,
                                    pip_subtitles=True, subtitle_language='fr')
        with closing(VideoContent(LocalFiles(path.parent), path.name)) as content:
            adapter = VideoProgress(content, video_root)
            (video_root / (adapter.fingerprint + '.json')).write_text(json.dumps({
                'schema': 1, 'revision': json.dumps(adapter.fingerprint), 'generation': '',
                'position': 4800, 'duration': 33000, 'settings': asdict(settings),
            }))
            self.assertEqual(adapter.load(), 4800)
            self.assertEqual(adapter.settings, settings)
            self.assertEqual(adapter.duration, 33000)
            external = dict(asdict(settings), audio_track=-1, audio_track_key='', subtitle_track=None,
                            subtitle_file='private-demo-captions.srt')
            VideoSettingsStore(adapter, video_root).save(external)
            adapter.save(20000, completed=True)
            adapter.retire()
        child = """
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
import json, sys
from commonUtils.runtime.resources.local import LocalFiles
from features.video.playback import VideoContent
from services.documents.video_progress import VideoProgress
path, root = map(Path, sys.argv[1:])
with closing(VideoContent(LocalFiles(path.parent), path.name)) as content:
    progress = VideoProgress(content, root)
    print(json.dumps([progress.load(), asdict(progress.settings)]))
"""
        output = subprocess.check_output([sys.executable, '-c', child, str(path), str(video_root)], text=True)
        self.assertEqual(json.loads(output), [0, external])
        self.assertEqual(SettingsStore(video_root).load(), PlaybackSettings())

    @stage(TestStage.EXTENDED)
    def test_localcrypt_legacy_checkpoint_and_private_track_options_survive_process_restart(self):
        from hashlib import sha256
        from features.video.playback import VideoContent
        from features.video.session import PlaybackSettings
        from services.documents.credential_state import CredentialState
        from services.documents.video_progress import VideoProgress
        from services.documents.video_settings import VideoSettingsStore
        from tests.local_crypt_fixture import crypt_fixture, require_pinned_rclone

        from io import BytesIO
        binary = require_pinned_rclone()
        video_root = self.cache / 'Video'
        movie = 'private-title.mkv'
        password = 'synthetic-package-password'
        with crypt_fixture(self.root, binary, state_password=password, pull=False) as fixture:
            fixture.provider.create_file(movie, BytesIO(b'video fixture' * 1000))
            with closing(VideoContent(fixture.provider, movie)) as content:
                adapter = VideoProgress(content, video_root)
                legacy = CredentialState(fixture.provider, adapter.fingerprint, self.cache,
                                         kind='video', revision=adapter.fingerprint)
                legacy.save(dict(position=5000, duration=44000,
                                 settings=asdict(PlaybackSettings(subtitle_track=-1))))
                self.assertEqual(adapter.load(), 5000)
                self.assertEqual(adapter.settings.subtitle_track, -1)
                preferences = asdict(PlaybackSettings(audio_track=2, audio_track_key='fr-commentary',
                                     subtitle_track=5, subtitle_track_key='fr-translation',
                                     subtitle_scale=1.75, subtitle_delay_ms=350, audio_delay_ms=-120,
                                     pip_subtitles=True))
                VideoSettingsStore(adapter, video_root).save(preferences)
                adapter.save(11000)
                adapter.retire()

            child = """
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
import json, sys
from features.rclone import session
from features.rclone.localcrypt import backend
from features.rclone.localcrypt.mapping import Connection
from features.video.playback import VideoContent
from services.documents.video_progress import VideoProgress
package, root, context, cache, binary = map(Path, sys.argv[1:6])
identity, movie = sys.argv[6:]
password = 'synthetic-package-password'
with patch.object(backend.configuration, 'get_credential_config_path', return_value=context.with_suffix('.conf')):
    item = Connection(package, 'Secret', root)
    session.remember(item.context, session.read_package(package, password), package_path=package,
                     state_password=password, state_identity=identity)
    with closing(backend.CryptResources(item, binary=binary)) as provider:
        with closing(VideoContent(provider, movie)) as content:
            progress = VideoProgress(content, cache / 'Video')
            print(json.dumps([progress.load(), progress.duration, asdict(progress.settings)]))
    session.forget(item.context)
"""
            identity = sha256(fixture.package.read_bytes()).hexdigest()
            output = subprocess.check_output([sys.executable, '-c', child, str(fixture.package),
                str(fixture.item.root), str(fixture.context), str(self.cache), str(binary), identity, movie], text=True)
            self.assertEqual(json.loads(output), [11000, 44000, preferences])
            from features.rclone.localcrypt.backend import CryptResources

            legacy_movie = 'old-path-checkpoint.mkv'
            with closing(CryptResources(fixture.item, binary=binary)) as provider:
                provider.create_file(legacy_movie, BytesIO(b'earlier video fixture' * 200))
                with closing(VideoContent(provider, legacy_movie)) as content:
                    old_path = CredentialState(provider, legacy_movie, self.cache,
                                               kind='video', revision=content.source.expected)
                    old_path.save(dict(position=7800, settings=preferences))
                    updated = VideoProgress(content, video_root)
                    self.assertEqual(updated.load(), 7800)
                    self.assertEqual(updated.settings.audio_track, 2)
                    self.assertEqual(VideoProgress(content, video_root).load(), 7800)

            encrypted = list((self.cache / 'ReaderPositions').glob('*.zip'))
            self.assertGreaterEqual(len(encrypted), 2)
            self.assertFalse(list((self.cache / 'ReaderPositions').rglob('*.json')))
            for path in encrypted:
                data = path.read_bytes()
                for secret in (movie.encode(), b'fr-commentary', b'fr-translation', b'subtitle_scale'):
                    self.assertNotIn(secret, data)

    def test_epub_migrates_legacy_passage_and_bookmarks_then_clear_retains_bookmarks(self):
        from features.books.epub import EPUBBook
        from features.books.preferences import ReadingState
        from features.books.ui.reader import BooksPage
        from services.documents.history_controls import clear_saved_positions
        from tests.books_fixture import make_book

        path = make_book(self.root / 'legacy.epub')
        book = EPUBBook(path)
        chapter = book.spine[1]
        mark = dict(label='Keep this', path=chapter, position=0, location=0)
        ReadingState(path, folder=self.cache).save(dict(path=chapter, position=0, location=0,
                                                       chapter=1, chapters=2, bookmarks=[mark]))
        first = BooksPage(state_folder=self.cache, initial_path=book)
        self.addCleanup(first.deleteLater)
        first.show()
        self.app.processEvents()
        self.assertEqual(first._path, chapter)
        first._save_state()
        self.assertEqual(first._state.load()['path'], chapter)
        self.assertEqual(first._state.load()['bookmarks'], [mark])
        clear_saved_positions(self.cache)
        first.close_reader()

        second = BooksPage(state_folder=self.cache, initial_path=EPUBBook(path))
        self.addCleanup(second.deleteLater)
        second.show()
        self.app.processEvents()
        self.assertEqual(second._current, 0)
        self.assertEqual(second._bookmarks, [mark])

    def test_comic_reopens_member_after_page_insertion_then_rejects_replacement(self):
        from io import BytesIO
        from PIL import Image
        from PySide6.QtTest import QTest
        from zipfile import ZipFile
        from features.comics.pages import ComicPages
        from features.comics.ui.reader import ComicReaderWindow

        path = self.root / 'comic.cbz'
        def write(pages):
            with ZipFile(path, 'w') as archive:
                for name, color in pages:
                    output = BytesIO()
                    Image.new('RGB', (50, 80), color).save(output, format='PNG')
                    archive.writestr(name, output.getvalue())

        def wait_for_page(window, index):
            for _ in range(200):
                if not window.busy and window.canvas.pixmaps and window.shown_page == index:
                    return
                QTest.qWait(20)
            self.fail(f'Page {index} was not displayed: {window.statusBar().currentMessage()}')

        pages = [('1.png', 'black'), ('2.png', 'blue'), ('3.png', 'green')]
        write(pages)
        first = ComicReaderWindow(ComicPages(path), state_folder=self.cache)
        first.show()
        wait_for_page(first, 0)
        first.go(2)
        wait_for_page(first, 2)
        first.shutdown()
        first.close()
        write([('0.png', 'red'), *pages])
        second = ComicReaderWindow(ComicPages(path), state_folder=self.cache)
        second.show()
        wait_for_page(second, 3)
        self.assertEqual(second.pages.pages[second.shown_page], '3.png')
        self.assertEqual(second.shown_page, 3)
        second.shutdown()
        second.close()
        write([('0.png', 'red'), *pages[:2], ('3.png', 'yellow')])
        third = ComicReaderWindow(ComicPages(path), state_folder=self.cache)
        third.show()
        wait_for_page(third, 0)
        third.shutdown()
        third.close()

    def test_desktop_text_reopens_the_same_cursor_and_scroll(self):
        from PySide6.QtTest import QTest
        from features.text_editor.ui.window import EditorWindow

        path = self.root / 'sample.txt'
        path.write_text(''.join(f'Line {index}.\n' for index in range(400)))
        def open_editor():
            editor = EditorWindow(create_blank=False, history_path=self.cache / 'text-recent.json',
                                  preferences_path=self.cache / 'text-options.ini')
            editor.open_path(path)
            for _ in range(200):
                if editor.current is not None and editor.current.position.ready:
                    return editor
                QTest.qWait(20)
            self.fail('Text viewport never became ready.')

        first = open_editor()
        cursor = first.current.editor.textCursor()
        cursor.setPosition(1470)
        first.current.editor.setTextCursor(cursor)
        first.current.editor.ensureCursorVisible()
        bar = first.current.editor.verticalScrollBar()
        self.assertGreater(bar.value(), 0)
        previous = bar.value() / bar.maximum()
        first.close()

        second = open_editor()
        self.assertEqual(second.current.editor.textCursor().position(), 1470)
        bar = second.current.editor.verticalScrollBar()
        self.assertAlmostEqual(bar.value() / bar.maximum(), previous, delta=.02)
        second.close()

    def test_explicit_subtitle_off_outlives_global_default_changes_and_copy_inherits(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from features.video.playback import VideoContent
        from features.video.session import PlaybackSettings
        from services.documents.video_progress import VideoProgress
        from services.documents.video_settings import SettingsStore, VideoSettingsStore

        root = self.cache / 'Video'
        defaults = SettingsStore(root)
        defaults.save(asdict(PlaybackSettings(subtitle_track=-1)))
        provider = LocalFiles(self.root)
        for name in ('original.mkv', 'copy.mkv'):
            (self.root / name).write_bytes(b'identical synthetic movie')
        with closing(VideoContent(provider, 'original.mkv')) as content:
            adapter = VideoProgress(content, root)
            adapter.load()
            store = VideoSettingsStore(adapter, root)
            store.save(asdict(store.load()), explicit={'subtitle_track'})

        defaults.save(asdict(PlaybackSettings(subtitle_track=2, subtitle_scale=1.75)))
        for name, track in (('original.mkv', -1), ('copy.mkv', 2)):
            with closing(VideoContent(provider, name)) as content:
                adapter = VideoProgress(content, root)
                adapter.load()
                self.assertEqual(adapter.settings.subtitle_track, track)
                self.assertEqual(adapter.settings.subtitle_scale, 1.75)

    def test_locked_reader_notice_reports_migration_and_clear_fence_stays_quiet(self):
        from types import SimpleNamespace
        from services.documents.ui.position_notice import position_notice

        state = SimpleNamespace(locked_state=True)
        self.assertIn('previous ZIP password', position_notice(state, 'locked'))
        self.assertEqual(position_notice(state, 'fenced'), '')
        state.locked_state = False
        self.assertIn('last saved position is retained', position_notice(state, 'write-failed'))
