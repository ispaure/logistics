"""Diagnostic provenance, lossless capture and unchanged original-suite routing."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import stat
import sys
from tempfile import TemporaryDirectory
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch
import zipfile

from logistics_build import ipad_lifetime_diagnostic as diagnostic

ROOT = Path(__file__).resolve().parents[3]


class DiagnosticBoundaryTests(unittest.TestCase):
    def test_owned_allocator_descriptor_preserves_history_after_source_unlink(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'allocator'
            source.mkdir()
            path = source / 'stack-log.index'
            path.write_bytes(b'actual allocator bytes')
            owner = diagnostic.AllocatorFiles()
            try:
                self.assertEqual(owner.observe(source), 22)
                path.unlink()
                records = owner.capture(root / 'captured')
                self.assertEqual((root / 'captured/inode-0').read_bytes(), b'actual allocator bytes')
                self.assertEqual(records[0]['original_name'], 'stack-log.index')
                self.assertEqual(records[0]['bytes'], 22)
            finally:
                owner.close()
            self.assertEqual(owner.files, {})

    def test_allocator_rejects_links_and_budget_overflow(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'real').write_bytes(b'large')
            owner = diagnostic.AllocatorFiles()
            try:
                with patch.object(diagnostic, 'MAX_ALLOCATOR', 1), self.assertRaisesRegex(ValueError, 'budget'):
                    owner.observe(root)
                (root / 'linked').symlink_to(root / 'real')
                with self.assertRaisesRegex(ValueError, 'links'):
                    owner.observe(root)
            finally:
                owner.close()

    def test_launch_environment_uses_only_noncompact_and_precreated_private_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            inherited = {'MallocStackLogging': '1', 'NSZombieEnabled': 'YES',
                         'SIMCTL_CHILD_MallocStackLogging': '1', 'SIMCTL_CHILD_NSZombieEnabled': 'YES'}
            with patch.dict(os.environ, inherited):
                environment, cache, trace, allocator = diagnostic.launch_environment(root / 'QA app.app', root / 'data')
            self.assertEqual(environment['SIMCTL_CHILD_MallocStackLoggingNoCompact'], '1')
            self.assertEqual(environment['SIMCTL_CHILD_MallocStackLoggingDirectory'], str(allocator))
            for key in inherited:
                self.assertNotIn(key, environment)
            self.assertTrue(allocator.is_dir())
            self.assertTrue(trace.is_file())
            self.assertEqual(trace.stat().st_mode & 0o777, 0o600)
            self.assertTrue(trace.is_relative_to(cache))
            self.assertIn('QA app.app', environment['SIMCTL_CHILD_DYLD_INSERT_LIBRARIES'])

    def test_hook_installation_requires_actual_native_initialization_and_requested_mode(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'trace'
            for text in ('', 'N 0x1 0 0 0 0 1\n', 'I 0x1 0 0 0 0 UIView.dealloc-installed-v1\nN 0x1 0 0 0 0 0\n',
                         'I 0x1 0 0 0 0 UIView.dealloc-installed-v1\nN 0x1 0 0 0 0 1\nF 0x1 0 0 0 0 bad-encoding\n'):
                path.write_text(text)
                self.assertFalse(diagnostic.trace_installed(path, 1))
            path.write_text('I 0x1 0 0 0 0 UIView.dealloc-installed-v1\nN 0x1 0 0 0 0 1\nG 0x1 0 0 0 0 \n')
            self.assertTrue(diagnostic.trace_installed(path, 1))

    def test_inherited_child_hook_records_cannot_establish_parent_initialization(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'trace'
            child = 'I 0x2 0 0 0 0 UIView.dealloc-installed-v1\nN 0x2 0 0 0 0 1\nG 0x2 0 0 0 0 \n'
            path.write_text(child)
            self.assertFalse(diagnostic.trace_installed(path, 1))
            self.assertTrue(diagnostic.trace_installed(path, 2))
            path.write_text(child + child.replace('0x2', '0x1'))
            self.assertTrue(diagnostic.trace_installed(path, 1))

    def test_native_trace_stacks_are_independent_for_identical_thread_and_pointer_in_other_pid(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'trace'
            path.write_text('E 0x1 0xabc 0x1 0 0 \nC 0x1 0xabc 0x1 0 0 ParentView\n'
                            'E 0x2 0xabc 0x1 0 0 \nC 0x2 0xabc 0x1 0 0 ChildView\n'
                            'X 0x1 0xabc 0x1 0 0 \n')
            result = diagnostic.summarize_trace(path)
            self.assertEqual(result['mismatched_records'], 0)
            self.assertEqual([(row['pid'], row['class_name']) for row in result['unmatched_candidates']],
                             [('0x2', 'ChildView')])

    def test_compile_argv_keeps_literal_paths_and_disables_arc(self):
        arguments = diagnostic.compile_command(Path('source & spaces.m'), Path('QA output.dylib'), Path('SDK path'))
        self.assertIn('-fno-objc-arc', arguments)
        self.assertNotIn('-fobjc-arc', arguments)
        self.assertEqual(arguments[-3:], ['source & spaces.m', '-o', 'QA output.dylib'])
        self.assertEqual(arguments[arguments.index('-isysroot') + 1], 'SDK path')

    def test_exact_original_source_native_binary_and_fixture_membership_are_required(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app, payload, fixtures = (root / name for name in ('QA.app', 'payload', 'fixtures'))
            fixture = app / 'app/tests/logisticsmobile'
            for path in (app / 'app/mobile', payload / 'mobile', fixtures, fixture):
                path.mkdir(parents=True, exist_ok=True)
            info = {'MainModule': 'tests.logisticsmobile'}
            (app / 'Info.plist').write_bytes(plistlib.dumps(info))
            (app / 'Logistics Mobile').write_bytes(b'original executable')
            source = dict(logistics_commit=diagnostic.BASE_SOURCE, commonUtils_commit=diagnostic.BASE_SHARED,
                          source_sha256=diagnostic.BASE_FINGERPRINT, dirty=False, commonUtils_dirty=False)
            for path in (payload / 'source.json', app / 'app/mobile/source.json'):
                path.write_text(json.dumps(source))
            (payload / 'mobile/owner.py').write_text('same')
            (app / 'app/mobile/owner.py').write_text('same')
            (fixtures / '__main__.py').write_text('original full suite')
            (fixture / '__main__.py').write_text('original full suite')
            with patch.object(diagnostic, 'BASE_BINARY', diagnostic.digest(app / 'Logistics Mobile')):
                actual, _, counts = diagnostic.verify_app(app, payload, fixtures)
                self.assertEqual(actual, source)
                self.assertEqual(counts, {'product_python': 1, 'fixture_python': 1})
                (fixture / 'extra.py').write_text('undeclared')
                with self.assertRaisesRegex(ValueError, 'membership'):
                    diagnostic.verify_app(app, payload, fixtures)
                (fixture / 'extra.py').unlink()
                (app / 'Logistics Mobile').write_bytes(b'foreign executable')
                with self.assertRaisesRegex(ValueError, 'identity'):
                    diagnostic.verify_app(app, payload, fixtures)

    def test_archive_rejects_parent_paths_and_escaping_links(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'app.zip'
            for name, target in (('../escape', None), ('QA.app/link', '/outside')):
                with zipfile.ZipFile(path, 'w') as archive:
                    info = zipfile.ZipInfo(name)
                    if target:
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, target or 'bytes')
                with self.assertRaises(ValueError):
                    diagnostic.safe_archive(path, root / 'extracted')

    def test_capture_precedes_cleanup_even_if_capture_fails(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            events = []
            client = Mock()
            client.remove.side_effect = lambda *_: events.append('remove')
            client.matching.return_value = None
            owner = Mock()
            owner.close.side_effect = lambda: events.append('close-fds')
            def collect(*args):
                events.append('capture')
                raise OSError('capture failed')
            receipt = {'diagnostic_only': True}
            with patch.object(diagnostic, 'collect', side_effect=collect):
                diagnostic.finish(root / 'cache', root, client, 'uuid', 'name', 12, 0, receipt, owner)
            self.assertEqual(events, ['capture', 'close-fds', 'remove'])
            self.assertEqual(receipt['capture_errors'], ['OSError'])
            self.assertEqual(receipt['cleanup'], 'verified-removed')
            self.assertTrue(json.loads((root / 'diagnostic-receipt.json').read_text())['diagnostic_only'])

    def test_native_trace_identifies_last_unmatched_view_without_dereferencing_it(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'trace'
            path.write_text('I 0x1 0 0 0 0 UIView.dealloc-installed-v1\n'
                            'E 0x1 0x111 0x1 0xa 0xb \nC 0x1 0x111 0x1 0xa 0xb ParentView\n'
                            'E 0x1 0x222 0x1 0xa 0xb \nC 0x1 0x222 0x1 0xa 0xb RetiredView\n'
                            'X 0x1 0x222 0x1 0xa 0xb \n')
            result = diagnostic.summarize_trace(path)
            self.assertEqual(result['mismatched_records'], 0)
            self.assertEqual([(row['pointer'], row['class_name']) for row in result['unmatched_candidates']],
                             [('0x111', 'ParentView')])
            self.assertTrue(result['diagnostic_only'])
            with path.open('a') as stream:
                stream.write('T trace-budget-exhausted\n')
            self.assertTrue(diagnostic.summarize_trace(path)['truncated'])

    def test_trace_parser_bounds_oversized_lines_and_total_bytes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'trace'
            path.write_bytes(b'E ' + b'x' * 10000)
            self.assertTrue(diagnostic.summarize_trace(path)['truncated'])
            path.write_bytes(b'E 0x1 0x1 0x1 0x1 0x1 \n' * 100)
            with patch.object(diagnostic, 'MAX_TRACE', 40):
                self.assertTrue(diagnostic.summarize_trace(path)['truncated'])

    def test_descriptor_close_error_still_cannot_skip_owned_simulator_cleanup(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            client = Mock()
            client.matching.return_value = None
            owner = Mock()
            owner.close.side_effect = OSError('descriptor failure')
            with patch.object(diagnostic, 'collect', return_value=[]):
                diagnostic.finish(root, root, client, 'uuid', 'name', 12, 0, {}, owner)
            client.remove.assert_called_once_with('uuid', 'name')

    def test_observer_preprocessing_failures_never_replace_or_repeat_original_actions(self):
        original = types.ModuleType('tests.logisticsmobile.__main__')
        original.exercise = AsyncMock()
        original.main = Mock()
        package = types.ModuleType('tests.logisticsmobile')
        package.__main__ = original
        modules = {'tests': types.ModuleType('tests'), 'tests.logisticsmobile': package,
                   'tests.logisticsmobile.__main__': original}
        path = ROOT / 'mobile_build/native_tests/diagnostics/ipad_lifetimes_entry.py'
        spec = importlib.util.spec_from_file_location('diagnostic_observer_fixture', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
        class RetiredContainer:
            @property
            def native(self):
                raise RuntimeError('observer cannot inspect retired native view')
        with TemporaryDirectory() as directory:
            for original_failure in (False, True):
                home = Mock(side_effect=ValueError('original product error') if original_failure else None,
                            return_value='original-home-result')
                picker = AsyncMock(return_value=True)
                release = Mock(return_value='original-release-result')
                adapter = types.SimpleNamespace(release_pane=release)
                # object() cannot be weak-referenced: preprocessing must fail
                # without escaping the observer or changing the original call.
                routes = types.SimpleNamespace(roots={'home': types.SimpleNamespace(children=[object()])})
                app = types.SimpleNamespace(paths=types.SimpleNamespace(cache=directory), routes=routes,
                    native_host=types.SimpleNamespace(adapter=adapter), show_home=home, open_hub_file=picker)
                module.install(app)
                if original_failure:
                    with self.assertRaisesRegex(ValueError, 'original product error'):
                        app.show_home('arg', flag=True)
                else:
                    self.assertEqual(app.show_home('arg', flag=True), 'original-home-result')
                home.assert_called_once_with('arg', flag=True)
                container = RetiredContainer()
                self.assertEqual(adapter.release_pane(container), 'original-release-result')
                release.assert_called_once_with(container)
                self.assertTrue(asyncio.run(app.open_hub_file('picker')))
                picker.assert_awaited_once_with('picker')

    def test_entry_calls_original_main_and_full_exercise_once_without_filtering(self):
        original = types.ModuleType('tests.logisticsmobile.__main__')
        calls = []
        async def full_suite(app):
            calls.append(('original-full-suite', app))
        sentinel = object()
        original.exercise = full_suite
        original.main = lambda: sentinel
        package = types.ModuleType('tests.logisticsmobile')
        package.__main__ = original
        modules = {'tests': types.ModuleType('tests'), 'tests.logisticsmobile': package,
                   'tests.logisticsmobile.__main__': original}
        path = ROOT / 'mobile_build/native_tests/diagnostics/ipad_lifetimes_entry.py'
        spec = importlib.util.spec_from_file_location('diagnostic_entry_fixture', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
        app = object()
        with patch.object(module, 'install', side_effect=lambda value: calls.append(('install', value))):
            asyncio.run(module.traced_exercise(app))
        self.assertIs(module.main(), sentinel)
        self.assertIs(original.exercise, module.traced_exercise)
        self.assertEqual(calls, [('install', app), ('original-full-suite', app)])
