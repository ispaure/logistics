"""Timing evidence for the host unittest runner; no application dependencies."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
from time import monotonic, perf_counter
import unittest


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def default_report(directory):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    root = Path(__file__).resolve().parents[2]
    return root / 'test-results' / 'test-timings' / f'{directory.name}-{stamp}-{os.getpid()}.json'


class TimingReport:
    def __init__(self, path, directory, pattern, isolated):
        self.path = path.resolve()
        self.started = perf_counter()
        self.data = {
            'schema_version': 1, 'started_at': timestamp(), 'finished_at': None,
            'directory': str(directory.resolve()), 'pattern': pattern,
            'isolated': isolated, 'python': sys.executable,
            'platform': platform.platform(), 'complete': False,
            'tests': [], 'modules': [],
        }

    def save(self, *, complete=False, exit_code=None):
        self.data.update(duration_seconds=perf_counter() - self.started,
                         complete=complete, exit_code=exit_code)
        if complete:
            self.data['finished_at'] = timestamp()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.data, indent=2) + '\n', encoding='utf-8')
        temporary.replace(self.path)

    def summarize(self):
        for key, title, name in (('tests', 'Slowest tests (setup, body and cleanup)', 'id'),
                                 ('modules', 'Slowest files (whole process)', 'path')):
            rows = sorted(self.data[key], key=lambda row: row['duration_seconds'], reverse=True)[:10]
            if rows:
                print(f'\n{title}:', flush=True)
                for row in rows:
                    print(f"  {row['duration_seconds']:8.3f}s  {row['outcome']:18} {row[name]}", flush=True)
        print(f'Timing report: {self.path}', flush=True)


class TimedResult(unittest.TextTestResult):
    """Include setup/teardown/cleanups, with fixture errors and subtest failures."""
    def startTest(self, test):
        self._timing = {'id': test.id(), 'started_at': timestamp(), 'outcome': 'incomplete'}
        self._started = perf_counter()
        self.status.update(test=test.id(), started=monotonic())
        super().startTest(test)

    def stopTest(self, test):
        self.report.data['tests'].append(dict(
            self._timing, duration_seconds=perf_counter() - self._started,
            finished_at=timestamp()))
        self._timing = None
        self.status['completed'] += 1
        self.status.update(test='between tests / class or module fixtures', started=monotonic())
        super().stopTest(test)

    def _outcome(self, test, outcome):
        if getattr(self, '_timing', None) is not None:
            if self._timing['outcome'] not in ('failed', 'error'):
                self._timing['outcome'] = outcome
        else:
            # unittest represents class/module fixture failures as synthetic tests.
            self.report.data['tests'].append({
                'id': test.id(), 'outcome': outcome, 'started_at': timestamp(),
                'finished_at': timestamp(), 'duration_seconds': 0.0,
                'fixture_event': True,
            })

    def addFailure(self, test, err):
        self._outcome(test, 'failed')
        super().addFailure(test, err)

    def addSuccess(self, test):
        self._outcome(test, 'passed')
        super().addSuccess(test)

    def addError(self, test, err):
        self._outcome(test, 'error')
        super().addError(test, err)

    def addSkip(self, test, reason):
        self._outcome(test, 'skipped')
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        self._outcome(test, 'expected_failure')
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self._outcome(test, 'unexpected_success')
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self._outcome(test, 'failed' if issubclass(err[0], test.failureException) else 'error')
        super().addSubTest(test, subtest, err)
