"""Compiled Pencil diagnostics are bounded, private and independent of contacts."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import asyncio
import gc
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch
from weakref import ref
from features.notebooks.mobile import ios_native_pen as module


class Feed:
    def __init__(self):
        self.closed = False
        self.window = object()
        self.view_id = 'a' * 32
        self.window_id = 'b' * 32
        self.value = {'native_producer': True, 'counts': {'raw_begin': 2, 'submitted': 3,
            'PRIVATE DOCUMENT': 1, 'raw_end': -1, 'timeout': True},
            'bindings': 1, 'queued_packets': 0, 'queued_samples': 0, 'inflight': 0,
            'coordinates': [11, 22], 'path': 'PRIVATE FILENAME'}
        self.web = NS(evaluate_javascript=Mock())
    def native_snapshot(self): return self.value


class NativeReporterTests(unittest.IsolatedAsyncioTestCase):
    def test_pending_uses_sequence_length_without_calling_python_count(self):
        binding = NS(pending=False, packets=[], touch=None)
        window = NS(notebookBindings=NS(objectForKey=lambda native: binding))
        feed = module.NativePencilFeed(NS(_impl=NS(native=object())), window, 'a' * 32)
        self.assertFalse(feed.pending)
        binding.packets.append(['down'])
        self.assertTrue(feed.pending)
        binding.packets.clear()
        binding.pending = True
        self.assertTrue(feed.pending)
        binding.pending = False
        binding.touch = object()
        self.assertTrue(feed.pending)
        binding.touch = None
        self.assertFalse(feed.pending)
        feed.closed = True
        self.assertFalse(feed.pending)

    def output(self):
        return Path(self.enterContext(TemporaryDirectory())) / 'notebook-input-diagnostics.json'

    def reporter(self, feed):
        output = self.output()
        output.write_text('{"stale_previous_build":true}')
        with patch('features.notebooks.mobile.ios_input._contact_class', side_effect=AssertionError('No Python contact observer')):
            reporter = module.NativePencilReporter(feed, asyncio.get_running_loop(), output)
        self.addCleanup(reporter.close)
        return reporter, output

    async def test_initial_receipt_replaces_stale_evidence_and_filters_content(self):
        feed = Feed(); reporter, output = self.reporter(feed)
        record = json.loads(output.read_text())
        self.assertNotIn('stale_previous_build', record)
        self.assertEqual(record['native']['view_id'], feed.view_id)
        self.assertEqual(record['native']['window_id'], feed.window_id)
        self.assertEqual(record['native']['counts'], {'raw_begin': 2, 'submitted': 3})
        self.assertEqual(record['native']['pairing'], 'separate-scopes')
        self.assertIn('window aggregate', record['native']['scope'])
        self.assertFalse(record['pair_stable'])
        self.assertNotIn('PRIVATE', output.read_text())
        self.assertNotIn('coordinates', output.read_text())
        self.assertEqual(len(reporter.observer_id), 32)

    async def test_hung_query_remains_single_flight_and_close_keeps_late_completion_safe(self):
        feed = Feed(); query = asyncio.get_running_loop().create_future()
        feed.web.evaluate_javascript.return_value = query
        reporter, output = self.reporter(feed)
        reporter.timer.cancel(); reporter.timer = None
        with patch.object(module.asyncio, 'wait', new=AsyncMock(return_value=(set(), {query}))):
            await reporter.poll()
        self.assertFalse(query.cancelled())
        self.assertEqual(feed.web.evaluate_javascript.call_count, 1)
        reporter.timer.cancel(); reporter.tick()
        self.assertEqual(feed.web.evaluate_javascript.call_count, 1)
        self.assertIs(reporter.query, query)
        feed.value['counts']['retired'] = 1
        reporter.close()
        closed = json.loads(output.read_text())
        self.assertTrue(closed['closed'])
        self.assertEqual(closed['native']['counts']['retired'], 1)
        query.set_result('{}'); await asyncio.sleep(0)
        self.assertEqual(json.loads(output.read_text()), closed)

    async def test_window_and_canvas_scopes_never_claim_equal_counts(self):
        feed = Feed(); query = asyncio.get_running_loop().create_future()
        query.set_result(json.dumps({'view_id': feed.view_id, 'counts': {'accepted-down:pen': 1}, 'recent': [], 'document': 'PRIVATE'}))
        feed.web.evaluate_javascript.return_value = query
        reporter, output = self.reporter(feed)
        reporter.timer.cancel(); reporter.timer = None
        await reporter.poll()
        record = json.loads(output.read_text())
        self.assertTrue(record['native']['dom_view_matches'])
        self.assertFalse(record['pair_stable'])
        self.assertIsNone(record['native_at_dom_query'])
        self.assertEqual(record['native']['window_counts_before_dom_query'], {'raw_begin': 2, 'submitted': 3})
        self.assertNotIn('PRIVATE', output.read_text())

    async def test_gone_weak_owner_closes_reporter_and_stops_timer(self):
        feed = Feed(); weak = ref(feed)
        reporter, output = self.reporter(feed)
        del feed; gc.collect()
        self.assertIsNone(weak())
        await reporter.poll()
        self.assertTrue(reporter.closed)
        self.assertIsNone(reporter.timer)
        self.assertTrue(json.loads(output.read_text())['closed'])

    async def test_scheduling_failure_never_escapes_or_leaves_partial_reporter(self):
        window = NS(unbindNotebookWebView=Mock())
        feed = module.NativePencilFeed(NS(_impl=NS(native=object())), window, 'a' * 32)
        feed.native_snapshot = Feed().native_snapshot
        output = self.output()
        self.assertFalse(feed.start_reporting(NS(call_later=Mock(side_effect=RuntimeError('scheduler unavailable'))), output))
        self.assertIsNone(feed.reporter)
        self.assertTrue(json.loads(output.read_text())['closed'])
        feed.close()

    async def test_reporter_failure_cannot_prevent_native_reference_release(self):
        native = object(); window = NS(unbindNotebookWebView=Mock())
        feed = module.NativePencilFeed(NS(_impl=NS(native=native)), window, 'a' * 32)
        feed.reporter = NS(close=Mock(side_effect=RuntimeError('optional diagnostics unavailable')))
        feed.close()
        window.unbindNotebookWebView.assert_called_once_with(native)
        self.assertIsNone(feed.web); self.assertIsNone(feed.window); self.assertIsNone(feed.reporter)

    async def test_gone_weak_owner_with_unresolved_query_does_not_rearm_tick(self):
        feed = Feed(); query = asyncio.get_running_loop().create_future()
        feed.web.evaluate_javascript.return_value = query
        reporter, output = self.reporter(feed)
        reporter.timer.cancel(); reporter.timer = None
        with patch.object(module.asyncio, 'wait', new=AsyncMock(return_value=(set(), {query}))):
            await reporter.poll()
        reporter.timer.cancel(); reporter.timer = None
        weak = ref(feed); del feed; gc.collect()
        self.assertIsNone(weak())
        reporter.tick()
        self.assertTrue(reporter.closed)
        self.assertIsNone(reporter.timer)
        self.assertFalse(query.cancelled())
        closed = json.loads(output.read_text())
        query.set_result('{}'); await asyncio.sleep(0)
        self.assertEqual(json.loads(output.read_text()), closed)

    async def test_native_foundation_boolean_accepts_rubicon_bool_or_integer_one_only(self):
        import sys
        from types import ModuleType
        objc = ModuleType('rubicon.objc'); objc.py_from_ns = lambda value: value
        value = {'native_producer': True, 'counts': {}}
        window = NS(notebookPencilSnapshot=lambda: value)
        feed = module.NativePencilFeed(NS(), window, 'a' * 32)
        with patch.dict(sys.modules, {'rubicon.objc': objc}):
            for flag in (True, 1):
                value['native_producer'] = flag
                self.assertIs(feed.native_snapshot(), value)
            for flag in (False, 0, 1.0, '1'):
                value['native_producer'] = flag
                with self.assertRaises(ValueError): feed.native_snapshot()
