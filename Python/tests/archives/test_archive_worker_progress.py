"""Cold encrypted creation must progress while Qt processes GUI events."""

from pathlib import Path
import sys

if __name__ == '__main__' and '--child' in sys.argv:
    sys.path[:0] = [str(Path(__file__).resolve().parents[2]),
                   str(Path(__file__).resolve().parents[3])]

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import json
import os
import subprocess
from tempfile import TemporaryDirectory
import unittest


def check_cold_creation(output):
    """Run the actual fixture with a worker admitted under a held-GIL schedule."""
    import threading
    import time
    from unittest.mock import patch
    from commonUtils.ui import pyside as qt
    from commonUtils.runtime.operations import OperationCancelled
    from features.archives.ui import create_zip
    from tests.archives.test_archive_password_ui import ArchivePasswordUITests

    ready, admitted = threading.Event(), threading.Event()
    report = dict(pid=os.getpid(), qt=qt.qVersion(), python=sys.version,
                  cold='pyzipper' not in sys.modules, deadline_seconds=5)
    original_create = create_zip.create_archive

    def create(*args, cancelled, **kwargs):
        ready.set()
        if not admitted.wait(10):
            raise TimeoutError('GUI never admitted its archive worker')
        if cancelled():
            raise OperationCancelled('Archive fixture cancelled')
        report['worker_started'] = time.monotonic()
        try:
            return original_create(*args, cancelled=cancelled, **kwargs)
        finally:
            report['worker_returned'] = time.monotonic()

    class ColdCreation(ArchivePasswordUITests):
        def wait(self, dialog):
            self.assertTrue(ready.wait(1), 'Archive worker did not enter')
            previous_interval = sys.getswitchinterval()
            try:
                # Make native Qt waits that retain the GIL visible without
                # relying on machine load. The real fixture keeps its 5s wait.
                sys.setswitchinterval(30)
                report['wait_started'] = time.monotonic()
                admitted.set()
                try:
                    super().wait(dialog)
                except AssertionError:
                    operation = dialog.task.operation
                    report['failure_worker_running'] = operation.isRunning() if operation else False
                    report['failure_worker_finished'] = operation.isFinished() if operation else True
                    # Cancel while still owning the GIL so failure cleanup
                    # cannot accidentally start and warm the cold backend.
                    dialog.reject()
                    raise
                finally:
                    report['wait_finished'] = time.monotonic()
            finally:
                admitted.set()
                sys.setswitchinterval(previous_interval)
            self.assertEqual(sys.getswitchinterval(), previous_interval)

    result = unittest.TestResult()
    with patch.object(create_zip, 'create_archive', side_effect=create):
        ColdCreation('test_creation_uses_config_and_keeps_source').run(result)
    report.update(tests=result.testsRun, failures=[text for _, text in result.failures],
                  errors=[text for _, text in result.errors])
    output.write_text(json.dumps(report, indent=2) + '\n')
    return 0 if result.wasSuccessful() and report['cold'] else 1


class ArchiveWorkerProgressTests(unittest.TestCase):
    def test_cold_encrypted_creation_keeps_its_five_second_deadline(self):
        with TemporaryDirectory(prefix='logistics-cold-archive-') as directory:
            root = Path(directory)
            output = root / 'result.json'
            environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', TMPDIR=str(root),
                               COMMONUTILS_STORAGE_ROOT=str(root / 'storage'),
                               XDG_CONFIG_HOME=str(root / 'config'), XDG_CACHE_HOME=str(root / 'cache'))
            completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child', str(output)],
                                       env=environment, capture_output=True, text=True, timeout=30)
            details = completed.stdout + completed.stderr
            if output.exists():
                details += '\n' + output.read_text()
            self.assertEqual(completed.returncode, 0, details)
            report = json.loads(output.read_text())
            self.progress_report = report
            self.assertTrue(report['cold'])
            self.assertEqual(report['tests'], 1)
            self.assertEqual(report['failures'], [])
            self.assertEqual(report['errors'], [])
            self.assertIn('worker_returned', report)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--child':
        from unittest.mock import patch
        output = Path(sys.argv[2])
        home = output.parent / 'home'
        home.mkdir(exist_ok=True)
        with patch.object(Path, 'home', return_value=home):
            raise SystemExit(check_cold_creation(output))
    unittest.main()
