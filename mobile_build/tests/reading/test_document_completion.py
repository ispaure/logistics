"""Reader status actions use the existing locators and playback checkpoints."""

import asyncio
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, get_ident
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from mobile.document_completion import commands, file_commands, item_progress, load_percentage, reference_target, tracked_kind
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
from services.documents.help_history import is_documentation
from services.documents.storage import FileItem

TEST_STAGE = TestStage.REGRESSION


class DocumentCompletionTests(TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.app = SimpleNamespace(private_root=self.root / 'state')
        self.provider = LocalFiles(self.root)

    def item(self, path):
        return FileItem(self.provider, path.name)

    def test_read_jumps_to_the_end_and_unread_resets_the_locator(self):
        epub, comic = make_books(self.root)
        for path in (epub, comic):
            with self.subTest(path=path.name):
                kind = tracked_kind(path)
                with item_progress(self.app, self.item(path), kind) as progress:
                    self.assertEqual(progress.percentage(), 0)
                    self.assertEqual(progress.mark(True), 'saved')
                with item_progress(self.app, self.item(path), kind) as reopened:
                    self.assertEqual(reopened.percentage(), 100)
                    saved = reopened.state.load()
                    self.assertEqual(saved['page'], reopened.count - 1)
                    self.assertEqual(saved['resource'], reopened.names[-1])
                    self.assertEqual(reopened.mark(False), 'saved')
                with item_progress(self.app, self.item(path), kind) as reopened:
                    self.assertEqual(reopened.percentage(), 0)
                    self.assertEqual(reopened.state.load()['page'], 0)
                    self.assertEqual(reopened.state.load()['resource'], reopened.names[0])

    def test_video_completion_survives_restarting_and_unwatched_clears_it(self):
        path = self.root / 'Fixture.mp4'
        path.write_bytes(b'Synthetic video data' * 512)
        expected = ['Mark as Watched', 'Mark as Unwatched']
        self.assertEqual([title for title, _ in file_commands(self.app, self.provider, self.provider.entry(path.name))],
                         expected)
        reference = reference_target(self.app, dict(type='local', path=str(path)))
        self.assertEqual([title for title, _ in commands(self.app, reference)], expected)
        with item_progress(self.app, self.item(path), 'video') as progress:
            progress.video.duration = 10000
            progress.video.save(3500)
            self.assertEqual(progress.percentage(), 35)
            self.assertEqual(progress.mark(True), 'saved')
        with item_progress(self.app, self.item(path), 'video') as reopened:
            self.assertEqual(reopened.percentage(), 100)
            reopened.video.save(0)
            reopened.video.save(1200)
        with item_progress(self.app, self.item(path), 'video') as replay:
            self.assertEqual(replay.percentage(), 100)
            self.assertEqual(replay.video.position, 1200)
            self.assertEqual(replay.mark(False), 'saved')
        with item_progress(self.app, self.item(path), 'video') as unread:
            self.assertEqual(unread.percentage(), 0)
            self.assertEqual(unread.video.position, 0)

    def test_epub_uses_text_progress_and_repairs_an_old_chapter_estimate(self):
        from features.books.mobile.pagination import MobilePagination

        first = 100 - len('Native EPUB first')
        second = 783 - len('Native EPUB second')
        epub, _ = make_books(self.root, chapter_text='a' * first, second_chapter_text='b' * second)
        with item_progress(self.app, self.item(epub), '.epub') as progress:
            self.assertEqual(progress.state.save(dict(page=0, resource=progress.names[0], offset=62,
                                                      percent=31)), 'saved')
            self.assertEqual(progress.percentage(), 7)
            reader = MobilePagination(progress.book, lambda _: None)
            reader.text_starts = (0, 100, 883)
            self.assertEqual(reader.percentage(0, 62), progress.percentage())
            reader.chapter = 1
            reader.bridge = SimpleNamespace(at_end=True)
            self.assertEqual(reader.percentage(1, 700), 100)
            self.assertEqual(progress.state.save(dict(page=1, resource=progress.names[1], offset=700,
                                                      percent=100)), 'saved')
            self.assertEqual(progress.percentage(), 100)

    def test_only_the_packaged_and_repository_wikis_are_excluded(self):
        repo = Path(__file__).resolve().parents[3]
        for relative in ('docs/user_mobile/documents/documents.md', 'docs/development/development.md',
                         'Python/mobile/help/docs/user_mobile/user_mobile.md'):
            self.assertTrue(is_documentation(dict(type='local', path=str(repo / relative))))
        self.assertFalse(is_documentation(dict(type='local', path=str(self.root / 'docs/user.md'))))
        self.assertFalse(is_documentation(dict(type='remote', key='docs/user.md')))


class CompletionLoadingTests(IsolatedAsyncioTestCase):
    async def test_slow_progress_read_leaves_the_event_loop_free_and_skips_retired_views(self):
        app = SimpleNamespace()
        loop, ui_thread = asyncio.get_running_loop(), get_ident()
        started, finish = asyncio.Event(), Event()
        reader_threads = []

        @contextmanager
        def target():
            reader_threads.append(get_ident())
            loop.call_soon_threadsafe(started.set)
            if not finish.wait(5):
                raise AssertionError('Progress blocked the UI event loop')
            yield SimpleNamespace(percentage=lambda: 7)

        visible = True
        first = asyncio.create_task(load_percentage(app, target, active=lambda: True))
        second = asyncio.create_task(load_percentage(app, target, active=lambda: visible))
        try:
            await asyncio.wait_for(started.wait(), 3)
            self.assertFalse(first.done())
            self.assertFalse(second.done())
            visible = False
        finally:
            finish.set()
            results = await asyncio.gather(first, second)
        self.assertEqual(results, [7, None])
        self.assertEqual(len(reader_threads), 1)
        self.assertNotEqual(reader_threads[0], ui_thread)
