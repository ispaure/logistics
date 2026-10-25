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
    def __init__(self, path, directory, pattern, isolated, junit=None):
        self.path = path.resolve()
        self.started = perf_counter()
        self.junit = junit
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
        if self.junit is not None:
            from build_manager.reporting import write_junit
            outcomes = {'passed': 'passed', 'failed': 'failed', 'error': 'error', 'skipped': 'skipped',
                        'expected_failure': 'skipped', 'unexpected_success': 'failed', 'incomplete': 'error'}
            cases = []
            for row in self.data['tests']:
                classname, _, name = row['id'].rpartition('.')
                cases.append(dict(name=name, classname=classname, status=outcomes[row['outcome']],
                                  seconds=row['duration_seconds'], message=row.get('message', '')))
            for row in self.data['modules']:
                if row['outcome'] != 'passed' or not row['test_report_complete']:
                    cases.append(dict(name=row['path'], classname='Logistics.runner', status='error',
                                      seconds=row['duration_seconds'], message='Isolated module: ' + row['outcome']))
            if not self.data['complete'] or not cases or (exit_code and all(row['status'] == 'passed' for row in cases)):
                cases.append(dict(name='suite_completion', classname='Logistics.runner', status='error',
                                  message='The suite did not complete successfully with case evidence.'))
            write_junit(self.junit, self.data['directory'], cases)

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
        self._detail(test, self._exc_info_to_string(err, test))
        super().addFailure(test, err)

    def addSuccess(self, test):
        self._outcome(test, 'passed')
        super().addSuccess(test)

    def addError(self, test, err):
        self._outcome(test, 'error')
        self._detail(test, self._exc_info_to_string(err, test))
        super().addError(test, err)

    def addSkip(self, test, reason):
        self._outcome(test, 'skipped')
        self._detail(test, reason)
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        self._outcome(test, 'expected_failure')
        self._detail(test, 'Expected failure: ' + self._exc_info_to_string(err, test))
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self._outcome(test, 'unexpected_success')
        self._detail(test, 'Unexpected success: update the declared expectation.')
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self._outcome(test, 'failed' if issubclass(err[0], test.failureException) else 'error')
            self._detail(test, str(subtest) + '\n' + self._exc_info_to_string(err, test))
        super().addSubTest(test, subtest, err)

    def _detail(self, test, message):
        row = self._timing if getattr(self, '_timing', None) is not None else self.report.data['tests'][-1]
        row['message'] = row.get('message', '') + message
