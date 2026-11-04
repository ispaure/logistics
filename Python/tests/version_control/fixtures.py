"""Offscreen Qt tests with real repositories and asynchronous UI lifecycle."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import unittest

from commonUtils.ui import pyside as qt
from features.git.repository import Repository, initialize
from features.git.ui.repository_view import RepositoryView


@unittest.skipUnless(shutil.which("git"), "Git executable required")
class GitUIFixture:
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])
        temporary = TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        root = Path(temporary.name)
        cls.repository_template = initialize(root / 'repo')
        repo = Repository(cls.repository_template)
        repo.run(['config', 'user.name', 'UI Test'])
        repo.run(['config', 'user.email', 'test@example.invalid'])
        repo.run(['config', 'commit.gpgsign', 'false'])
        repo.run(['config', 'core.hooksPath', str(root / 'no-hooks')])
        repo.run(['symbolic-ref', 'HEAD', 'refs/heads/main'])

    def setUp(self):
        self.temp = self.temporary_directory()
        self.root = Path(self.temp.name)
        # Copy the empty repository, including .git: each case owns its refs,
        # index, configuration and working files, with no shared writable state.
        self.repo = Repository(shutil.copytree(self.repository_template, self.root / 'repo'))
        self.page = RepositoryView(preferences_path=self.root / 'git.json')
        self.page.resize(1250, 800)
        self.page.show()
        self.page.activateWindow()
        self.addCleanup(self.release_page)

    def release_page(self):
        self.page.changes.message.clear()
        self.page.prepare_close()
        self.wait()
        self.page.close()
        self.page.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def wait(self, timeout=10):
        deadline = monotonic() + timeout
        while True:
            self.app.processEvents()
            if not self.page.busy and not self.page.file_timer.isActive() and not self.page._refresh_pending:
                break
            self.assertLess(monotonic(), deadline, 'Git worker did not finish')
            sleep(.005)

    def open(self):
        self.page.open_repository(self.repo.path)
        self.wait()
        self.assertIsNotNone(self.page.snapshot, self.page.status.text())

    def commit_fixture(self):
        (self.repo.path / 'file.txt').write_text('first\n')
        self.repo.stage(['file.txt'])
        self.repo.commit('First')
