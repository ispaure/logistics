"""Real Qt Notes rows use native items, retain collapsed children and avoid bodies."""
import json
import os
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.notes_library.ui.notes_library import NotesLibraryWindow
from logistics_build.build_retention import scratch

TEST_STAGE = TestStage.EXTENDED


class FirstTreePaint(qt.QObject):
    def __init__(self, tree):
        super().__init__(tree)
        self.armed, self.elapsed = False, None
        tree.viewport().installEventFilter(self)

    def start(self, *, armed=False):
        self.started = perf_counter()
        self.elapsed, self.armed = None, armed

    def eventFilter(self, watched, event):
        if self.armed and event.type() == qt.QEvent.Type.Paint:
            self.elapsed, self.armed = perf_counter() - self.started, False
        return False


class DesktopRowRenderingTests(QtTestCase):
    def fixture(self, provider, count, *, private=False):
        paths = [f'Library/Folder/Note {i:04}.md' for i in range(count)]
        folders = ['Library', 'Library/Folder'] + [f'Library/Folder/Child {i}' for i in range(4)]
        paths += [f'Library/Folder/Child {i}/Child {i}.md' for i in range(4)]
        if private:
            for folder in folders:
                provider._physical(folder, directory=True).mkdir(parents=True, exist_ok=True)
            data = provider.encrypted_path('note.md').read_bytes()
            for encoded in provider._commands.encode_many(paths):
                (provider.root / encoded).write_bytes(data)
        else:
            for folder in folders:
                (provider.root / folder).mkdir(parents=True, exist_ok=True)
            for path in paths:
                (provider.root / path).write_text('# Synthetic fixture')

    def exercise(self, provider, count, storage):
        window = NotesLibraryWindow(lambda: provider, 'Synthetic rows', root='Library')
        window.show()
        self.wait_until(lambda: not window.progress.busy)
        folder = window.items['Library/Folder']
        qt.QApplication.instance().processEvents()
        clock = FirstTreePaint(window.tree)
        populate = window.populate
        publications, row_seconds = [], []

        def publish(path, rows, pages=None):
            start = perf_counter()
            result = populate(path, rows, pages)
            row_seconds.append(perf_counter() - start)
            publications.append((path, len(rows)))
            clock.armed = True
            return result

        widgets = len(qt.QApplication.allWidgets())
        with patch.object(provider, 'open', side_effect=AssertionError('Expansion read a document body')), \
                patch.object(window, 'populate', side_effect=publish):
            clock.start()
            folder.setExpanded(True)
            self.wait_until(lambda: clock.elapsed is not None and not window.progress.busy, timeout=30)
        cold = clock.elapsed
        self.assertEqual(publications, [('Library/Folder', count + 4)])
        self.assertEqual(folder.childCount(), count + 4)
        self.assertLess(len(qt.QApplication.allWidgets()) - widgets, 8)
        children = [folder.child(i) for i in range(folder.childCount())]
        self.assertTrue(all(window.tree.itemWidget(child, 0) is None for child in children))
        self.assertTrue(all(window.tree.indexWidget(window.tree.indexFromItem(child)) is None for child in children))
        folder.setExpanded(False)
        qt.QApplication.instance().processEvents()
        with patch.object(window, 'list_folder', side_effect=AssertionError('Repeated expansion relisted provider')):
            clock.start(armed=True)
            folder.setExpanded(True)
            self.wait_until(lambda: clock.elapsed is not None)
        self.assertEqual(children, [folder.child(i) for i in range(folder.childCount())])
        report = dict(storage=storage, rows=count + 4, cold_first_paint_seconds=cold,
                      repeated_first_paint_seconds=clock.elapsed, row_construction_seconds=sum(row_seconds),
                      per_row_widgets=0, repeated_rows_retained=True,
                      platform=qt.QApplication.platformName())
        window.close()
        self.wait_until(lambda: not __import__('shiboken6').isValid(window), drain_deferred=True)
        return report

    def test_local_and_encrypted_native_tree_rows(self):
        from features.rclone import executable
        from tests.local_crypt_fixture import crypt_fixture
        results = []
        with scratch(Path.cwd()) as workspace:
            local = workspace / 'local'
            local.mkdir()
            provider = LocalFiles(local)
            self.fixture(provider, 40)
            results.append(self.exercise(provider, 40, 'local'))
            binary = executable.get_rclone_path()
            if not binary.is_file():
                if os.environ.get('LOGISTICS_REQUIRE_LOCALCRYPT_TESTS'):
                    self.fail('Required pinned rclone is missing')
                self.skipTest('Optional pinned rclone is not installed')
            encrypted = workspace / 'encrypted'
            encrypted.mkdir()
            with crypt_fixture(encrypted, binary, pull=False) as fixture:
                self.fixture(fixture.provider, 40, private=True)
                results.append(self.exercise(fixture.provider, 40, 'localcrypt'))
            if path := os.environ.get('LOGISTICS_NOTES_ROW_REPORT'):
                Path(path).write_text(json.dumps(results, indent=2) + '\n')
