"""Real filesystem events refresh clean tracked files without refresh feedback loops."""
from unittest.mock import patch
from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from tests.version_control.fixtures import GitUIFixture

TEST_STAGE = TestStage.REGRESSION


class GitWatcherTests(GitUIFixture, QtTestCase):
    def test_clean_file_edit_refreshes_status_automatically(self):
        self.commit_fixture()
        self.open()
        file = self.repo.path / 'file.txt'
        self.assertIn(str(file.resolve()), self.page.watch.files())
        changes = []
        self.page.watch.fileChanged.connect(changes.append)
        file.write_text('first edit\n')
        # Watcher delivery and the asynchronous Git snapshot have separate budgets.
        # Slow Git processes must not masquerade as missing filesystem events.
        self.wait_until(lambda: bool(changes), message='No filesystem notification for the tracked file')
        self.wait()
        self.assertEqual(self.page.snapshot.status.changes[0].path, 'file.txt')

    def test_manual_refresh_does_not_retrigger_itself(self):
        from time import monotonic, sleep
        self.commit_fixture()
        # Make the index's stat data stale, the condition under which ordinary
        # git status would rewrite it and notify the .git directory watcher.
        # Touch before installing watchers, so genuine file-edit notifications
        # cannot be mistaken for refreshes caused by the manual snapshot.
        file = self.repo.path / 'file.txt'
        file.touch()
        index = self.repo.path / '.git' / 'index'
        original_index = index.read_bytes()
        self.open()
        with patch.object(self.page, '_job', wraps=self.page._job) as jobs:
            self.page.refresh(); self.wait()
            deadline = monotonic() + 2
            while monotonic() < deadline:
                self.app.processEvents(); sleep(.01)
            self.wait()
            # Native watchers can deliver an initial burst of notifications.
            # Verify that it settles, rather than assuming one event per edit.
            settled_jobs = jobs.call_count
            deadline = monotonic() + 2
            while monotonic() < deadline:
                self.app.processEvents(); sleep(.01)
            self.wait()
            self.assertEqual(jobs.call_count, settled_jobs,
                             [call.args[0] for call in jobs.call_args_list])
        self.assertEqual(index.read_bytes(), original_index)
        self.assertFalse(self.page.file_timer.isActive())
        self.assertFalse(self.page._refresh_pending)
