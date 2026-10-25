"""Timing diagnostics preserve results, failures and nested elapsed accounting."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from mobile_build.native_tests.tests.logisticsmobile.timings import SuiteTimings, measure


class NativeSuiteTimingsTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'timings.json'
        self.now = 0
        self.events = []
        self.timer = SuiteTimings(self.path, clock=lambda: self.now,
                                 emit=lambda event, **kwargs: self.events.append(event))

    def test_nested_sections_report_inclusive_and_exclusive_time(self):
        with self.timer.section('rotation'):
            self.now = 1
            with self.timer.section('rotation-request', panel='settings', orientation='portrait'):
                self.now = 3
            self.now = 5
        rows = self.timer.summary()['sections']
        self.assertEqual([(r['name'], r['elapsed_s'], r['self_s']) for r in rows],
                         [('rotation', 5, 3), ('rotation-request', 2, 2)])
        self.assertEqual(json.loads(self.path.read_text())['records'][1]['parent'], 'rotation')

    def test_failure_is_persisted_and_propagates_without_becoming_a_pass(self):
        with self.assertRaisesRegex(AssertionError, 'unsafe control'):
            with self.timer.section('geometry'):
                self.now = 4
                raise AssertionError('unsafe control')
        row = json.loads(self.path.read_text())['records'][0]
        self.assertEqual(row['status'], 'AssertionError')
        self.assertEqual(row['elapsed_s'], 4)
        self.assertEqual(self.timer.summary()['sections'][0]['failures'], 1)
        self.assertFalse(self.timer.active)

    def test_checkpoints_measure_since_previous_successful_case(self):
        self.now = 2
        self.timer.checkpoint('hub')
        self.now = 7
        self.timer.checkpoint('documents')
        self.assertEqual([r['since_previous_case_s'] for r in self.timer.checkpoints], [2, 5])

    def test_orientation_samples_aggregate_by_panel_without_losing_count(self):
        for orientation in ('portrait', 'landscape-left'):
            with self.timer.section('rotation-request', panel='settings', orientation=orientation):
                self.now += 1
        summary = self.timer.summary()['sections']
        self.assertEqual(len(summary), 1)
        self.assertEqual((summary[0]['count'], summary[0]['elapsed_s']), (2, 2))
        self.assertEqual(len(json.loads(self.path.read_text())['records']), 2)

    def test_measure_executes_once_and_returns_original_result(self):
        calls = []
        async def operation():
            calls.append('executed')
            self.now = 3
            return object_result
        object_result = object()
        result = asyncio.run(measure(SimpleNamespace(_native_suite_timings=self.timer), 'fixture', operation()))
        self.assertIs(result, object_result)
        self.assertEqual(calls, ['executed'])
        self.assertEqual(self.timer.records[0]['elapsed_s'], 3)

    def test_cancelled_checks_remain_cancelled(self):
        async def operation():
            raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(measure(SimpleNamespace(_native_suite_timings=self.timer), 'fixture', operation()))
        self.assertEqual(self.timer.records[0]['status'], 'CancelledError')


class TimingReportTests(unittest.TestCase):
    def test_report_and_crash_cache_use_same_non_overlapping_sort_order(self):
        from mobile_build.validation.native_timing_report import summarize
        summary = dict(elapsed_s=8, note='Nested totals overlap', sections=[
            dict(name='rotation', self_s=2, elapsed_s=8),
            dict(name='request', self_s=6, elapsed_s=6)])
        for report in (dict(timings=summary), dict(summary=summary), summary):
            with self.subTest(report=report):
                result = summarize(report)
                self.assertEqual([r['name'] for r in result['sections']], ['request', 'rotation'])
                self.assertEqual(result['elapsed_s'], 8)
        self.assertEqual(summary['sections'][0]['name'], 'rotation')
