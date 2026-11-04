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

    def test_budget_overrun_is_persisted_before_rejection_and_capture_keeps_explicit_truncated_prefix(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'allocator'
            source.mkdir()
            path = source / 'stack-log.index'
            path.write_bytes(b'0123456789')
            owner = diagnostic.AllocatorFiles(root / 'growth.json')
            try:
                with patch.object(diagnostic, 'MAX_ALLOCATOR', 4), patch.object(diagnostic, 'MAX_TRUNCATED_CAPTURE', 3):
                    with self.assertRaisesRegex(ValueError, 'logical budget'):
                        owner.observe(source)
                    growth = json.loads((root / 'growth.json').read_text())
                    self.assertEqual(growth['samples'][-1]['logical_bytes'], 10)
                    self.assertEqual(growth['latest']['file_count'], 1)
                    self.assertEqual(growth['latest']['allocated_bytes'], path.stat().st_blocks * 512)
                    records = owner.capture(root / 'captured')
                self.assertEqual(records[0]['logical_bytes'], 10)
                self.assertEqual(records[0]['captured_bytes'], 3)
                self.assertTrue(records[0]['truncated'])
                self.assertFalse(records[0]['complete'])
                self.assertEqual((root / 'captured/inode-0.TRUNCATED').read_bytes(), b'012')
                metadata = json.loads((root / 'captured/capture-metadata.json').read_text())
                self.assertFalse(metadata['complete'])
                self.assertTrue(metadata['history_incomplete'])
                self.assertEqual(metadata['reason'], 'allocator-logical-budget')
                self.assertEqual(metadata['captured_bytes'], 3)
            finally:
                owner.close()

    def test_overbudget_prefix_is_bounded_across_all_files_together(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'allocator'
            source.mkdir()
            (source / 'first').write_bytes(b'first')
            (source / 'second').write_bytes(b'second')
            owner = diagnostic.AllocatorFiles()
            try:
                with patch.object(diagnostic, 'MAX_ALLOCATOR', 4), patch.object(diagnostic, 'MAX_TRUNCATED_CAPTURE', 3):
                    with self.assertRaises(ValueError):
                        owner.observe(source)
                    records = owner.capture(root / 'captured')
                self.assertEqual(sum(row['captured_bytes'] for row in records), 3)
                self.assertEqual(sum(row['logical_bytes'] for row in records), 11)
                self.assertTrue(all(row['truncated'] for row in records))
            finally:
                owner.close()

    def test_logical_and_allocated_growth_are_distinct_and_sample_history_is_bounded(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'allocator'
            source.mkdir()
            path = source / 'sparse-history'
            with path.open('wb') as stream:
                stream.seek(1024 * 1024 - 1)
                stream.write(b'x')
            owner = diagnostic.AllocatorFiles(root / 'growth.json')
            try:
                with patch.object(diagnostic, 'MAX_GROWTH_SAMPLES', 2):
                    for _ in range(4):
                        owner.observe(source)
                growth = json.loads((root / 'growth.json').read_text())
                self.assertEqual(len(growth['samples']), 2)
                self.assertEqual(growth['latest']['logical_bytes'], 1024 * 1024)
                self.assertEqual(growth['latest']['allocated_bytes'], path.stat().st_blocks * 512)
                self.assertEqual(growth['latest']['files'][0]['st_blocks'], path.stat().st_blocks)
                self.assertIn('not RAM', growth['note'])
            finally:
                owner.close()

    def test_disk_reserve_rejection_persists_actual_free_sample_and_keeps_incomplete_prefix(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'allocator'
            source.mkdir()
            (source / 'history').write_bytes(b'0123456789')
            owner = diagnostic.AllocatorFiles(root / 'growth.json', scratch_path=root)
            try:
                with patch.object(diagnostic.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=diagnostic.MIN_DISK_RESERVE - 1)):
                    with self.assertRaisesRegex(ValueError, 'disk reserve'):
                        owner.observe(source)
                growth = json.loads((root / 'growth.json').read_text())
                sample = growth['samples'][-1]
                self.assertEqual(sample['scratch_free_bytes'], diagnostic.MIN_DISK_RESERVE - 1)
                self.assertEqual(sample['output_free_bytes'], diagnostic.MIN_DISK_RESERVE - 1)
                self.assertEqual(sample['logical_bytes'], 10)
                with patch.object(diagnostic, 'MAX_TRUNCATED_CAPTURE', 3):
                    owner.capture(root / 'captured')
                metadata = json.loads((root / 'captured/capture-metadata.json').read_text())
                self.assertEqual(metadata['reason'], 'disk-reserve')
                self.assertFalse(metadata['complete'])
                self.assertEqual(metadata['captured_bytes'], 3)
                self.assertEqual((root / 'captured/inode-0.TRUNCATED').read_bytes(), b'012')
            finally:
                owner.close()

    def test_scratch_preflight_records_actual_free_bytes_before_admission_failure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = {'diagnostic_only': True}
            with patch.object(diagnostic.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=12)):
                with self.assertRaisesRegex(RuntimeError, '12 GiB'):
                    diagnostic.require_scratch_space(root, root / 'output', receipt)
            actual = json.loads((root / 'output/disk-preflight.json').read_text())
            self.assertEqual(actual['free_bytes'], 12)
            self.assertEqual(actual['minimum_free_bytes'], 12 * 1024 ** 3)
            self.assertEqual(receipt['disk_preflight'], actual)

    def test_scratch_preflight_accepts_exact_minimum_without_mutating_external_storage(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = {'diagnostic_only': True}
            with patch.object(diagnostic.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=diagnostic.MIN_SCRATCH_FREE)):
                metadata = diagnostic.require_scratch_space(root, root / 'output', receipt)
            self.assertEqual(metadata['free_bytes'], diagnostic.MIN_SCRATCH_FREE)

    def test_free_space_for_capture_cannot_masquerade_as_complete_history(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'allocator'
            source.mkdir()
            (source / 'history').write_bytes(b'0123456789')
            owner = diagnostic.AllocatorFiles()
            try:
                owner.observe(source)
                with patch.object(diagnostic.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=0)):
                    records = owner.capture(root / 'captured')
                metadata = json.loads((root / 'captured/capture-metadata.json').read_text())
                self.assertFalse(metadata['complete'])
                self.assertEqual(metadata['captured_bytes'], 0)
                self.assertEqual(metadata['reason'], 'insufficient-free-space-for-complete-copy')
                self.assertTrue(records[0]['truncated'])
            finally:
                owner.close()

    def test_source_growth_during_copy_is_labeled_incomplete(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'allocator'
            source.mkdir()
            path = source / 'history'
            path.write_bytes(b'old')
            owner = diagnostic.AllocatorFiles()
            real_read = diagnostic.os.read
            def changing_read(descriptor, amount):
                block = real_read(descriptor, amount)
                with path.open('ab') as stream:
                    stream.write(b'new')
                return block
            try:
                owner.observe(source)
                with patch.object(diagnostic.os, 'read', side_effect=changing_read):
                    records = owner.capture(root / 'captured')
                self.assertEqual(records[0]['captured_bytes'], 3)
                self.assertEqual(records[0]['source_logical_bytes_after'], 6)
                self.assertTrue(records[0]['source_changed_during_capture'])
                self.assertFalse(records[0]['complete'])
                self.assertTrue(records[0]['retained_file'].endswith('.TRUNCATED'))
                metadata = json.loads((root / 'captured/capture-metadata.json').read_text())
                self.assertFalse(metadata['complete'])
                self.assertFalse(metadata['atomic_allocator_snapshot'])
            finally:
                owner.close()

    def test_fd_limit_is_still128_and_rejecting_sample_retains_extra_file_metadata(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'allocator'
            source.mkdir()
            for number in range(129):
                (source / str(number)).write_bytes(b'x')
            owner = diagnostic.AllocatorFiles(root / 'growth.json')
            try:
                with self.assertRaisesRegex(ValueError, 'Too many'):
                    owner.observe(source)
                self.assertEqual(len(owner.files), 128)
                growth = json.loads((root / 'growth.json').read_text())
                self.assertEqual(growth['latest']['file_count'], 129)
                self.assertEqual(growth['latest']['open_fds'], 128)
                self.assertTrue(growth['latest']['file_count_is_lower_bound'])
                owner.capture(root / 'captured')
                captured = json.loads((root / 'captured/capture-metadata.json').read_text())
                self.assertFalse(captured['complete'])
                self.assertEqual(len(captured['unopened_files']), 1)
                self.assertEqual(json.loads((root / 'growth.json').read_text())['latest']['file_count'], 129)
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

    def test_reviewed_release_parent_owns_reusable_mobile_artifact_but_other_sources_and_workflows_fail(self):
        parent = dict(id=41819543378, head_sha=diagnostic.BASE_SOURCE,
                      path='.github/workflows/release.yml', workflow_id=186613344)
        diagnostic.verify_source_run(parent)
        diagnostic.verify_source_run(dict(parent, path='.github/workflows/mobile-build.yml'))
        with self.assertRaisesRegex(ValueError, 'original 43a source'):
            diagnostic.verify_source_run(dict(parent, head_sha='b' * 40))
        with self.assertRaisesRegex(ValueError, 'unreviewed workflow'):
            diagnostic.verify_source_run(dict(parent, path='.github/workflows/docs-checks.yml'))

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
