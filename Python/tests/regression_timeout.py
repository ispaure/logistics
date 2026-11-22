"""Capture bounded diagnostics from an owned stalled macOS test child."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "marcandre.voyer@gmail.com"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from contextlib import ExitStack, contextmanager
import faulthandler
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from time import monotonic
import unittest
from unittest.mock import patch
from uuid import uuid4

from regression_timing import timestamp

CAPTURE_DIRECTORY = 'timeout-capture'
MAX_STACK = 64 * 1024
SAMPLE_LEAD = 5


def output_root(path, stage):
    target = Path(__file__).parent / 'editing/test_notes_library_tabs.py'
    results = os.environ.get('LOGISTICS_PLATFORM_RESULTS')
    if (sys.platform == 'darwin' and os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('QT_QPA_PLATFORM') == 'offscreen' and results
            and stage == 'regression' and path.resolve() == target.resolve()):
        return Path(results).resolve() / 'native' / 'test-timeouts'
    return None


class Checkpoints:
    def __init__(self, directory):
        self.path = directory / 'checkpoint.json'
        self.recent = []

    def __call__(self, phase, test=None):
        self.recent.append(dict(phase=phase, test=test, at=timestamp()))
        self.recent = self.recent[-6:]
        try:
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.recent), encoding='utf-8')
            temporary.replace(self.path)
        except OSError as error:
            print(f'Timeout diagnostic checkpoint failed ({type(error).__name__}).', file=sys.stderr, flush=True)


@contextmanager
def child_checkpoints(directory):
    """Record case and teardown boundaries without handling any test exception."""
    checkpoint = Checkpoints(directory)
    with ExitStack() as stack:
        try:
            stream = stack.enter_context((directory / 'python.log').open('wb', buffering=0))
            # A request can arrive after unregister but before process exit.
            signal.signal(signal.SIGUSR1, signal.SIG_IGN)
            faulthandler.register(signal.SIGUSR1, file=stream, all_threads=True)
        except (OSError, RuntimeError, ValueError) as error:
            print(f'Timeout diagnostic stack setup failed ({type(error).__name__}).',
                  file=sys.stderr, flush=True)
            yield None
            return
        stack.callback(faulthandler.unregister, signal.SIGUSR1)
        checkpoint('child-ready')

        def record_before(method, phase):
            original = getattr(unittest.TestCase, method)

            def run(test, *args, **kwargs):
                checkpoint(phase, test.id())
                return original(test, *args, **kwargs)

            stack.enter_context(patch.object(unittest.TestCase, method, run))

        record_before('_callTearDown', 'teardown-started')
        record_before('doCleanups', 'cleanup-started')
        yield checkpoint


def _read(path, limit):
    with path.open('rb') as stream:
        return stream.read(limit + 1)


def _sample(process, directory, remaining):
    errors = []
    if remaining < .5:
        return ['Insufficient time to collect stacks before the test deadline.']
    if (directory / 'checkpoint.json').is_file():
        try:
            # Do not reap the child before sample attaches. Its PID stays
            # reserved even if it exits between these two requests.
            os.kill(process.pid, signal.SIGUSR1)
        except OSError as error:
            errors.append(f'Python signal failed ({type(error).__name__}).')
    else:
        errors.append('Python signal handler readiness was not recorded.')
    try:
        # Write the raw sample only inside the disposable workspace. The
        # retained log includes only call stacks from this owned process.
        subprocess.run(['/usr/bin/sample', str(process.pid), '1', '10', '-file',
                        str(directory / 'sample.txt')],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True, timeout=min(3, remaining - .25))
    except (OSError, subprocess.SubprocessError) as error:
        errors.append(f'Native sample failed ({type(error).__name__}).')
    return errors


def _publish(directory, output, file, stage, errors):
    label = uuid4().hex
    checkpoints, artifacts = [], {}
    try:
        recent = json.loads(_read(directory / 'checkpoint.json', 4096))
        if (not isinstance(recent, list) or not 1 <= len(recent) <= 6
                or any(not isinstance(item, dict) or set(item) != {'phase', 'test', 'at'}
                       for item in recent)):
            raise ValueError('Unexpected checkpoint.')
        checkpoints = recent
    except (OSError, ValueError) as error:
        errors.append(f'Cannot read case checkpoints ({type(error).__name__}).')
    result = dict(file=file, stage=stage, checkpoints=checkpoints, artifacts=artifacts, errors=errors)
    try:
        output.mkdir(parents=True, exist_ok=True)
        for kind, name in (('python', 'python.log'), ('native', 'sample.txt')):
            try:
                data = _read(directory / name, MAX_STACK)
                truncated = len(data) > MAX_STACK
                data = data[:MAX_STACK]
                if kind == 'native':
                    # Native sample metadata and binary/dependency inventory
                    # are unnecessary. Preserve only the call graph.
                    data = data.partition(b'Call graph:')[2]
                    for separator in (b'Total number in stack', b'Sort by top of stack', b'Binary Images:'):
                        data = data.partition(separator)[0]
                if not data.strip():
                    raise ValueError('Empty stack.')
                path = output / f'{label}-{kind}.log'
                path.write_bytes(data)
                artifacts[kind] = dict(file=path.name, truncated=truncated)
            except (OSError, ValueError) as error:
                errors.append(f'Cannot retain {kind} stack ({type(error).__name__}).')
        result['status'] = 'incomplete' if errors else 'captured'
        report = output / f'{label}.json'
        report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        result['receipt'] = str(report)
    except OSError as error:
        errors.append(f'Cannot publish timeout diagnostics ({type(error).__name__}).')
        result['status'] = 'incomplete'

    print(f'Timeout diagnostics [{result["status"]}] for {file} [{stage}]: '
          + str(result.get('receipt', 'receipt unavailable')), file=sys.stderr, flush=True)
    for error in errors:
        print(error, file=sys.stderr, flush=True)
    return result


def _wait_until(process, deadline, cancelled):
    while True:
        if cancelled is not None and cancelled.is_set():
            return 130
        remaining = max(0, deadline - monotonic())
        try:
            return process.wait(timeout=remaining if cancelled is None else min(.1, remaining))
        except subprocess.TimeoutExpired:
            if monotonic() >= deadline:
                return None


def monitored_child(command, environment, timeout, directory, output, file, stage, cancelled):
    """Sample just before the existing deadline, preserving exit and interrupts."""
    from parallel_regressions import _posix_child

    try:
        directory.mkdir()
    except OSError as error:
        print(f'Timeout diagnostic directory setup failed ({type(error).__name__}).', file=sys.stderr, flush=True)
        errors = ['Cannot initialize timeout capture directory.']
    else:
        errors = []
    with _posix_child(command, environment) as process:
        deadline = monotonic() + timeout
        if not errors:
            code = _wait_until(process, deadline - SAMPLE_LEAD, cancelled)
            if code is not None:
                return code, None
            errors = _sample(process, directory, deadline - monotonic())
        code = _wait_until(process, deadline, cancelled)
        if code is not None:
            return code, None
    return 124, _publish(directory, output, file, stage, errors)
