"""Native provisioning proves verified inputs and ownership without real SDK downloads."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import zipfile

from logistics_build import native_tooling as owner
from logistics_build import tooling_bootstrap as bootstrap


class NativeToolingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.mobile = self.root / 'mobile_build/.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        self.mobile.parent.mkdir(parents=True)
        self.mobile.touch()
        self.work = self.root / 'scratch'
        self.work.mkdir()
        self.spec = owner.declared()
        self.enterContext(patch.object(owner, 'host_key', return_value='darwin-arm64'))
        self.downloads = []

    @contextmanager
    def scratch(self, root):
        self.assertEqual(root, self.root)
        try:
            yield self.work
        finally:
            import shutil
            shutil.rmtree(self.work)

    def wheel(self, output, *, tag='py3-none-any', binary=False):
        path = output / ('langdetect-1.0.9-' + tag + '.whl')
        with zipfile.ZipFile(path, 'w') as target:
            target.writestr('langdetect/__init__.py', '# portable fixture\n')
            target.writestr('langdetect-1.0.9.dist-info/METADATA', 'Name: langdetect\nVersion: 1.0.9\n')
            target.writestr('langdetect-1.0.9.dist-info/WHEEL', 'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: ' + tag + '\n')
            if binary:
                target.writestr('langdetect/unsafe.so', b'binary')
        return path

    def prepared_wheel(self):
        folder = self.root / 'mobile_build/.tools/release-wheels'
        folder.mkdir(parents=True)
        wheel = self.wheel(folder)
        receipt = dict(schema=1, filename=wheel.name, source_sha256=self.spec['langdetect']['sha256'], wheel_sha256=owner.digest(wheel))
        (folder / owner.WHEEL_RECEIPT).write_text(json.dumps(receipt))
        return wheel, folder / owner.WHEEL_RECEIPT

    def download(self, record, path):
        self.downloads.append(record['filename'])
        if record['filename'].startswith('go'):
            with tarfile.open(path, 'w:gz') as target:
                data = b'fixture Go binary'
                member = tarfile.TarInfo('go/bin/' + ('go.exe' if os.name == 'nt' else 'go'))
                member.size = len(data)
                member.mode = 0o755
                target.addfile(member, io.BytesIO(data))
        else:
            path.write_bytes(b'verified source fixture')

    def command(self, argv, **kwargs):
        if argv[1:] == ['version']:
            return NS(returncode=0, stdout='go version go1.26.9 darwin/arm64\n')
        self.assertEqual(argv[1:4], ['-m', 'pip', 'wheel'])
        for arg in ('--no-deps', '--no-build-isolation', '--no-index'):
            self.assertIn(arg, argv)
        self.assertEqual(kwargs['env']['PIP_NO_INDEX'], '1')
        self.wheel(Path(argv[argv.index('--wheel-dir') + 1]))
        return NS(returncode=0)

    def test_explicit_repair_provisions_once_then_reuses_verified_bytes(self):
        with patch('logistics_build.build_retention.scratch', self.scratch), \
                patch.object(owner, 'download', side_effect=self.download), \
                patch.object(owner.shutil, 'which', return_value=None), \
                patch.object(owner.subprocess, 'run', side_effect=self.command):
            result = owner.provision(self.root)
        self.assertTrue(result['ready'])
        self.assertEqual(len(self.downloads), 2)
        self.assertFalse(self.work.exists())
        self.assertTrue((self.root / 'mobile_build/.tools/go' / owner.GO_MARKER).is_file())
        with patch.object(owner, 'download', side_effect=AssertionError('Unnecessary download')), \
                patch.object(owner.subprocess, 'run', side_effect=self.command), \
                patch('logistics_build.build_retention.scratch', side_effect=AssertionError('Ready state needs no scratch')):
            self.assertTrue(owner.provision(self.root)['ready'])

    def test_pinned_download_rejects_corruption_and_size_before_publish(self):
        source = b'archive'
        record = dict(filename='go.tar.gz', size=len(source), sha256='0' * 64)
        with patch.object(owner.urllib.request, 'urlopen', return_value=io.BytesIO(source)):
            with self.assertRaises(ValueError):
                owner.download(record, self.work / 'download')
        self.assertFalse((self.root / 'mobile_build/.tools/go').exists())

    def test_archive_traversal_and_links_cannot_escape_scratch(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('go/bin/go', tarfile.SYMTYPE)]:
            with self.subTest(name=name, kind=kind):
                archive = self.work / 'bad.tar.gz'
                with tarfile.open(archive, 'w:gz') as target:
                    member = tarfile.TarInfo(name); member.type = kind; member.linkname = '/outside'
                    target.addfile(member)
                with self.assertRaises(ValueError):
                    owner.extract_go(archive, self.work / ('extract-' + str(kind)))
        self.assertFalse((self.root / 'escape').exists())

    def test_wheel_receipt_detects_changed_bytes_source_and_platform(self):
        wheel, receipt = self.prepared_wheel()
        self.assertTrue(owner.wheel_status(self.root)['ready'])
        wheel.write_bytes(b'changed')
        self.assertFalse(owner.wheel_status(self.root)['ready'])
        self.wheel(wheel.parent)
        data = json.loads(receipt.read_text()); data['source_sha256'] = '0' * 64
        receipt.write_text(json.dumps(data))
        self.assertFalse(owner.wheel_status(self.root)['ready'])
        with self.assertRaises(ValueError):
            owner.wheel_metadata(self.wheel(self.work, tag='py3-none-macosx_11_0_arm64'))
        with self.assertRaises(ValueError):
            owner.wheel_metadata(self.wheel(self.work, binary=True))

    def test_exact_external_go_selector_is_preserved_without_download(self):
        external = self.root / 'external'; (external / 'bin').mkdir(parents=True)
        (external / 'bin' / ('go.exe' if os.name == 'nt' else 'go')).touch()
        selector = self.root / 'mobile_build/.tools/go'; selector.parent.mkdir(parents=True)
        selector.symlink_to(external, target_is_directory=True)
        self.prepared_wheel()
        with patch.object(owner.subprocess, 'run', side_effect=self.command), \
                patch.object(owner, 'download', side_effect=AssertionError('Do not replace user SDK')):
            self.assertTrue(owner.provision(self.root)['ready'])
        self.assertTrue(selector.is_symlink())
        self.assertFalse((external / owner.GO_MARKER).exists())

    def test_wrong_existing_go_and_unowned_wheel_paths_are_never_replaced(self):
        selector = self.root / 'mobile_build/.tools/go'; selector.mkdir(parents=True)
        keep = selector / 'personal'; keep.write_text('preserve')
        with patch.object(owner.subprocess, 'run', side_effect=OSError('wrong SDK')), \
                patch.object(owner, 'download', side_effect=AssertionError('No download on conflict')):
            with self.assertRaisesRegex(ValueError, 'conflicts'):
                owner.provision(self.root)
        self.assertEqual(keep.read_text(), 'preserve')

    def test_unsupported_and_desktop_only_never_download(self):
        self.mobile.unlink()
        with patch.object(owner, 'download', side_effect=AssertionError('No mobile env')):
            self.assertFalse(owner.provision(self.root)['applicable'])
        self.mobile.touch()
        with patch.object(owner, 'host_key', return_value='unsupported'), \
                patch.object(owner, 'download', side_effect=AssertionError('Unsupported host')):
            self.assertFalse(owner.provision(self.root)['applicable'])

    def test_bootstrap_hook_uses_owned_mobile_child_and_guarded_runner(self):
        with patch.object(bootstrap, 'run', return_value='{}') as run, \
                patch.object(bootstrap, '_MUTATION', NS(get=lambda: dict(value=dict(nonce='fixture-nonce')))):
            bootstrap.repair_native(self.root)
        self.assertEqual(run.call_args.args[0], [self.mobile, self.root / 'logistics_build/native_tooling.py', '--root', self.root, '--owner-nonce', 'fixture-nonce'])
        self.assertEqual(run.call_args.kwargs['cwd'], self.root)

    def test_go_probe_disables_network_telemetry_and_rejects_wrong_version(self):
        go = self.work / 'go'; go.touch()
        with patch.object(owner.shutil, 'which', return_value=str(go)), \
                patch.object(owner.subprocess, 'run', return_value=NS(returncode=0, stdout='go version go1.27.0 darwin/arm64')) as run:
            self.assertFalse(owner.go_status(self.root)['ready'])
        self.assertEqual(run.call_args.kwargs['env']['GOTOOLCHAIN'], 'local')
        self.assertEqual(run.call_args.kwargs['env']['GOTELEMETRY'], 'off')
        self.assertEqual(run.call_args.kwargs['timeout'], 10)

    def test_failed_wheel_build_preserves_go_and_publishes_no_partial_receipt(self):
        def failing(argv, **kwargs):
            if argv[1:] == ['version']:
                return self.command(argv, **kwargs)
            raise subprocess.CalledProcessError(1, argv)
        with patch('logistics_build.build_retention.scratch', self.scratch), \
                patch.object(owner, 'download', side_effect=self.download), \
                patch.object(owner.shutil, 'which', return_value=None), \
                patch.object(owner.subprocess, 'run', side_effect=failing):
            with self.assertRaises(subprocess.CalledProcessError):
                owner.provision(self.root)
        self.assertTrue((self.root / 'mobile_build/.tools/go' / owner.GO_MARKER).is_file())
        self.assertFalse((self.root / 'mobile_build/.tools/release-wheels').exists())
        self.assertFalse(self.work.exists())

    def test_unowned_wheel_directory_is_preserved_and_blocks_download(self):
        folder = self.root / 'mobile_build/.tools/release-wheels'
        folder.mkdir(parents=True); (folder / 'personal.whl').write_text('preserve')
        with patch.object(owner, 'go_status', return_value=dict(ready=True)), \
                patch.object(owner, 'download', side_effect=AssertionError('No mutation')):
            with self.assertRaisesRegex(ValueError, 'unverified'):
                owner.provision(self.root)
        self.assertEqual((folder / 'personal.whl').read_text(), 'preserve')

    def test_readonly_receipt_can_be_selected_from_canonical_outside_snapshot(self):
        wheel, _ = self.prepared_wheel()
        snapshot = self.root / 'snapshot'; snapshot.mkdir()
        self.assertTrue(owner.wheel_status(snapshot, directory=wheel.parent)['ready'])

    def test_early_gate_rejects_missing_wheel_despite_ready_tool_versions(self):
        from logistics_build import native_prerequisites as gate
        go = self.work / 'go'; go.touch()
        def version(argv, **kwargs):
            text = ('go version go1.26.9 darwin/arm64' if argv[1:] == ['version'] else
                    'pip 26.3 from fixture' if argv[2] == 'pip' else '0.4.5')
            return NS(returncode=0, stdout=text, stderr='')
        with patch.object(gate.shutil, 'which', return_value=str(go)), \
                patch.object(gate.subprocess, 'run', side_effect=version):
            result = gate.inspect(str(self.mobile), 'native', wheel_directory=self.root / 'missing')
        self.assertFalse(result['ready'])
        self.assertTrue(all(row['ready'] for row in result['tools'] if row['tool'] != 'langdetect-wheel'))
        self.assertFalse(next(row for row in result['tools'] if row['tool'] == 'langdetect-wheel')['ready'])

    def test_standalone_mutation_without_owner_lock_is_rejected(self):
        lock = bootstrap.lock_path(self.root)
        lock.parent.mkdir(parents=True)
        lock.touch()
        with self.assertRaisesRegex(ValueError, 'repair lock'):
            owner.require_owner(self.root, 'invented')

    def test_manifest_matches_host_and_native_contract_versions(self):
        from logistics_build.native_prerequisites import EXPECTED
        self.assertEqual(self.spec['go_version'], EXPECTED['go'])
        lock=(owner.ROOT/'mobile_build/requirements-host.txt').read_text()
        self.assertIn(self.spec['langdetect']['sha256'],lock)
        self.assertEqual(set(self.spec['go']),{'darwin-arm64','darwin-amd64','linux-arm64','linux-amd64','windows-arm64','windows-amd64'})

    def test_project_selector_wins_over_an_unrelated_path_go(self):
        selector=self.root/'mobile_build/.tools/go';selector.mkdir(parents=True)
        with patch.object(owner.shutil,'which',side_effect=AssertionError('Do not fall back from explicit selector')), \
                patch.object(owner.subprocess,'run',side_effect=OSError('Missing selected binary')):
            result=owner.go_status(self.root)
        self.assertFalse(result['ready'])
        self.assertEqual(result['executable'],str(owner.go_path(self.root)))

    @unittest.skipUnless(os.name=='posix','POSIX owned group identity')
    def test_child_authorization_requires_matching_nonce_and_owned_group(self):
        identity=dict(nonce='correct',groups=[dict(pgid=os.getpgrp(),sid=os.getsid(0))])
        with patch.object(bootstrap,'file_lock',side_effect=bootstrap.ActiveWorkflowError()), \
                patch.object(bootstrap,'read_intent',return_value=identity):
            owner.require_owner(self.root,'correct')
            with self.assertRaisesRegex(ValueError,'mutation identity'):
                owner.require_owner(self.root,'wrong')

    def test_doctor_reports_native_selection_separately_from_python_imports(self):
        from contextlib import redirect_stdout
        from Scripts.development import doctor
        output=io.StringIO()
        probe=NS(returncode=0,stdout='{"python":"3.12.2","missing":[]}')
        native=dict(applicable=True,ready=False,go=dict(ready=False,expected='1.26.9',executable='selected-go'),wheel=dict(ready=True))
        with patch('Scripts.development.subprocess.run',return_value=probe), \
                patch('Scripts.development.find_uv',return_value='uv'), \
                patch.object(owner,'status',return_value=native) as inspected,redirect_stdout(output):
            self.assertEqual(doctor(self.root,lambda _: self.mobile),1)
        inspected.assert_called_once_with(self.root)
        self.assertIn('MISSING native prerequisites:',output.getvalue())
        self.assertIn('selected-go',output.getvalue())
        self.assertIn('1.26.9',output.getvalue())

    def test_windows_redirector_chain_uses_root_nonce_not_immediate_parent(self):
        capability=bootstrap.private(self.root)/'native-setup-owner.json'
        capability.parent.mkdir(parents=True)
        capability.write_text(json.dumps(dict(schema=1,root=str(self.root),nonce='correct')))
        with patch.object(owner.sys,'platform','win32'), \
                patch.object(owner.os,'getppid',side_effect=AssertionError('Redirector parent is not the bootstrap')), \
                patch.object(bootstrap,'file_lock',side_effect=bootstrap.ActiveWorkflowError()):
            owner.require_owner(self.root,'correct')
            with self.assertRaisesRegex(ValueError,'launch capability'):
                owner.require_owner(self.root,'wrong')
            capability.write_text(json.dumps(dict(schema=1,root='/unrelated',nonce='correct')))
            with self.assertRaisesRegex(ValueError,'launch capability'):
                owner.require_owner(self.root,'correct')
        capability.write_text(json.dumps(dict(schema=1,root=str(self.root),nonce='correct')))
        lock=bootstrap.lock_path(self.root);lock.touch()
        with patch.object(owner.sys,'platform','win32'):
            with self.assertRaisesRegex(ValueError,'repair lock'):
                owner.require_owner(self.root,'correct')
