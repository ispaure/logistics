"""Cold Android compiler cache resolves the host created by the real build step."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from logistics_build import mobile_runtime


class AndroidRuntimePrepareTests(unittest.TestCase):
    def prepare_fixture(self, *, conflicting_directory=False):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cache, result = root / 'cache', root / 'result.json'
            cache.mkdir()
            pin = json.loads(Path(mobile_runtime.__file__).with_name('mobile_runtime_tools.json').read_text())['cpython']
            host = cache / 'cross-build/build/python.exe'
            library = cache / 'cross-build' / pin['android_target'] / 'prefix/lib/libpython3.14.so'
            if conflicting_directory:
                (host.parent / 'python').mkdir(parents=True)
                library.parent.mkdir(parents=True)
                library.write_bytes(b'previous library')
            def build(argv, cwd, timeout):
                self.assertEqual(cwd, cache)
                if argv[3] == 'build':
                    host.parent.mkdir(parents=True, exist_ok=True)
                    host.write_bytes(b'compiled host')
                    host.chmod(0o700)
                else:
                    library.parent.mkdir(parents=True, exist_ok=True)
                    library.write_bytes(b'compiled Android library')
            def query(argv, **kwargs):
                if argv[0] == 'xcrun':
                    return str(root / 'sdk')
                self.assertEqual(argv[0], str(host))
                self.assertTrue(host.is_file())
                return pin['version']
            with patch.object(mobile_runtime, 'source'), patch.object(mobile_runtime, 'runtime_wheels'), patch.object(
                    mobile_runtime, 'command', side_effect=build) as command, patch.object(
                    mobile_runtime.subprocess, 'check_output', side_effect=query), patch.dict(
                    'os.environ', DEVELOPER_DIR=str(root / 'developer')):
                mobile_runtime.prepare(cache, result)
                self.assertEqual(json.loads(result.read_text())['host_sha256'], mobile_runtime.checksum(host))
                self.assertEqual(command.call_count, 2)
                mobile_runtime.prepare(cache, result)
                self.assertTrue(json.loads(result.read_text())['reused'])
                self.assertEqual(command.call_count, 2)
                host.write_bytes(b'changed interpreter')
                with self.assertRaisesRegex(ValueError, 'artifacts changed'):
                    mobile_runtime.prepare(cache, result)

    def test_cold_build_resolves_new_executable_and_reuses_only_verified_artifacts(self):
        self.prepare_fixture()

    def test_directory_named_python_does_not_count_as_a_compiled_interpreter(self):
        self.prepare_fixture(conflicting_directory=True)


class AndroidRuntimePolicyTests(unittest.TestCase):
    def test_testbed_keeps_project_payload_arguments_and_exact_source_acceptance(self):
        from mobile_build import tools
        for changed in (False, True):
            with self.subTest(changed_source=changed), TemporaryDirectory() as directory:
                root = Path(directory)
                cache = root / 'cache'
                cache.mkdir()
                output = root / 'result.json'
                manifest = {'source_sha256': 'a' * 64}
                report = {'source': {'source_sha256': 'b' * 64} if changed else manifest}
                with patch.object(tools, 'stage', return_value=manifest) as stage, patch.object(
                        tools, 'verify', return_value=report) as verify, patch.object(
                        mobile_runtime, 'runtime_wheels', return_value=root / 'wheels'), patch.object(
                        mobile_runtime, 'command') as command, patch.object(
                        mobile_runtime, 'native_command') as launch:
                    launch.return_value = 0
                    if changed:
                        with self.assertRaisesRegex(ValueError, 'source identity changed'):
                            mobile_runtime.test(root, cache, 'caller-serial', output)
                    else:
                        mobile_runtime.test(root, cache, 'caller-serial', output)
                    stage.assert_called_once_with(root, root / 'runtime-payload', testbed=True, allow_dirty=True)
                    argv = launch.call_args.args[0]
                    self.assertEqual(argv[argv.index('--') + 1:],
                        ['-m', 'mobile.smoke', '--target', 'android', '--local-source-sha256', manifest['source_sha256']])
                    self.assertEqual(argv[4], 'caller-serial')
                    self.assertEqual(command.call_args.args[0][-2:], ['markdown-it-py==4.2.0', 'mdurl==0.1.2'])
                    verify.assert_called_once_with(output.with_suffix('.log'), 'android', output,
                                                   local_manifest=root / 'runtime-payload/source.json')
                    self.assertEqual(launch.call_args.args[2], 1800)
                    self.assertFalse(launch.call_args.kwargs['check'])
