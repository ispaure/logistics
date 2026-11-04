"""Exercise real Archives fixture failure cleanup inside an isolated Qt process."""

import argparse
import faulthandler
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from threading import Event
import time
import unittest
from unittest.mock import patch


SENTINEL = 'Controlled archive fixture assertion before worker retirement'
CASES = (
    ('password', 'test_creation_uses_config_and_keeps_source'),
    ('lifecycle', 'test_zip_suggests_stem_and_prompts_without_configuration'),
    ('lifecycle', 'test_folder_zip_keeps_root_and_uses_config_without_prompt'),
)


def source_hashes(targets):
    paths = [child for target in targets
             for child in (target.rglob('*') if target.is_dir() else (target,)) if child.is_file()]
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main(output):
    # Only the child imports Qt. A native abort must become a parent regression
    # failure, rather than destroy the process running the rest of the suite.
    root = Path(__file__).resolve().parents[3]
    sys.path[:0] = [str(root / 'Python'), str(root)]
    from commonUtils.ui import pyside as qt
    from commonUtils.runtime.operations import OperationCancelled
    from tests.archives.test_archive_password_ui import ArchivePasswordUITests
    from tests.archives.test_archive_zip_creation_lifecycle import ZipCreationLifecycleTests

    app = qt.QApplication.instance() or qt.QApplication([])
    report = dict(pid=os.getpid(), qt=qt.qVersion(), python=sys.version,
                  platform=platform.platform(), qpa=app.platformName(), cases=[])
    output.parent.mkdir(parents=True, exist_ok=True)

    for owner, method in CASES:
        entered, cancelled_seen, retired = Event(), Event(), Event()
        state = dict(case=method)

        def work(targets, destination, *, cancelled, **kwargs):
            original = source_hashes(targets)
            entered.set()
            try:
                # Bound a broken cleanup too: it must produce a useful failure,
                # never leave an immortal test worker behind.
                deadline = time.monotonic() + 10
                while not cancelled() and time.monotonic() < deadline:
                    time.sleep(.005)
                if not cancelled():
                    raise TimeoutError('Fixture never cancelled its active archive worker')
                cancelled_seen.set()
                state['sources_preserved'] = source_hashes(targets) == original
                state['output_published'] = Path(destination).exists()
                raise OperationCancelled('Controlled fixture cancellation')
            finally:
                retired.set()

        class FailureDuringCreation:
            def wait(self, dialog):
                self.wait_until(entered.is_set, message='Archive fixture worker did not enter')
                state['fixture'] = self.temp.name
                state['running_before_assertion'] = dialog.task.operation.isRunning()
                state['finished_before_assertion'] = dialog.task.operation.isFinished()
                dialog.destroyed.connect(lambda: state.update(destroyed_after_retirement=retired.is_set()))
                self.assertTrue(state['running_before_assertion'])
                self.assertFalse(state['finished_before_assertion'])
                self.fail(SENTINEL)

        base = ArchivePasswordUITests if owner == 'password' else ZipCreationLifecycleTests
        case_type = type('FailureDuringCreation', (FailureDuringCreation, base), {})

        class PreservedResult(unittest.TestResult):
            def addFailure(self, case, error):
                super().addFailure(case, error)
                # Checkpoint the primary assertion before cleanup can abort.
                state.setdefault('primary_failure', self.failures[-1][1])
                output.write_text(json.dumps(report, indent=2) + '\n')

        report['cases'].append(state)
        result = PreservedResult()
        with patch('features.archives.ui.create_zip.create_archive', side_effect=work):
            case_type(method).run(result)
        state.update(failures=len(result.failures), errors=len(result.errors),
                     failure_details=[detail for _, detail in result.failures],
                     error_details=[detail for _, detail in result.errors],
                     cancellation_observed=cancelled_seen.is_set(), worker_retired=retired.is_set(),
                     fixture_removed=not Path(state.get('fixture', '/missing-fixture')).exists())
        output.write_text(json.dumps(report, indent=2) + '\n')
        valid = (state['failures'] == 1 and state['errors'] == 0
                 and SENTINEL in state.get('primary_failure', '')
                 and state.get('running_before_assertion') is True
                 and state.get('finished_before_assertion') is False
                 and state['cancellation_observed'] and state['worker_retired']
                 and state.get('destroyed_after_retirement') is True
                 and state['fixture_removed'] and state.get('sources_preserved') is True
                 and state.get('output_published') is False)
        if not valid:
            return 1
    report['status'] = 'passed'
    output.write_text(json.dumps(report, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    faulthandler.enable(all_threads=True)
    # Match the owning runner's private-home isolation even when invoked alone.
    home = args.output.parent / 'home'
    home.mkdir(parents=True, exist_ok=True)
    with patch.object(Path, 'home', return_value=home):
        raise SystemExit(main(args.output))
