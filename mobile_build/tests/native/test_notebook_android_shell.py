"""Python-only notebook restaging preserves frozen Android implementation bytes."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from mobile_build.validation import notebook_template_tools as tools


class NotebookAndroidShellTests(unittest.TestCase):
    def test_selected_probe_and_frozen_revision_preserve_dex_and_libraries(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            apk = root / 'original.apk'
            with ZipFile(apk, 'w') as archive:
                archive.writestr('classes.dex', b'compiled production Java')
                archive.writestr('lib/arm64-v8a/libpython.so', b'native library')
                archive.writestr('assets/chaquopy/app.imy', b'old Python')
            source = dict(logistics_commit='compiled', commonUtils_commit='shared',
                          dirty=False, commonUtils_dirty=False)
            receipt = root / 'receipt.json'
            receipt.write_text(json.dumps(dict(apk=str(apk), sha256=sha256(apk.read_bytes()).hexdigest(), source=source)))
            (root / 'source.json').write_text(json.dumps(dict(source, logistics_commit='frozen')))
            prepared = []
            repacker = SimpleNamespace(prepare=lambda apk, work, **kwargs: prepared.append(kwargs) or apk)
            def run(argv, **kwargs):
                if 'sign' in argv:
                    (root / 'notebook.apk').write_bytes(apk.read_bytes())
            with patch.object(tools.importlib.util, 'module_from_spec', return_value=repacker), \
                 patch.object(tools.importlib.util, 'spec_from_file_location', return_value=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module: None))), \
                 patch.object(tools.subprocess, 'check_output', return_value='') as diff, \
                 patch.object(tools.subprocess, 'run', side_effect=run), \
                 patch('mobile_build.deployment.android_deploy.build_tools', return_value=root):
                signed = tools.android_shell(receipt, root, root, root, {}, probe='notebook_calibration_probe')
            self.assertEqual(prepared, [dict(probe='notebook_calibration_probe')])
            self.assertEqual(diff.call_args.args[0][5:7], ['compiled', 'frozen'])
            self.assertEqual(tools.compiled_payload(signed), tools.compiled_payload(apk))
            report = json.loads((root / 'compiled-payload.json').read_text())
            self.assertTrue(report['unchanged'])
            self.assertEqual(set(report['entries']), {'classes.dex', 'lib/arm64-v8a/libpython.so'})

    def test_changed_compiled_java_is_rejected_before_restaging(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            apk = root / 'original.apk'
            apk.write_bytes(b'original')
            source = dict(logistics_commit='compiled', commonUtils_commit='shared', dirty=False, commonUtils_dirty=False)
            receipt = root / 'receipt.json'
            receipt.write_text(json.dumps(dict(apk=str(apk), sha256=sha256(apk.read_bytes()).hexdigest(), source=source)))
            (root / 'source.json').write_text(json.dumps(dict(source, logistics_commit='frozen')))
            with patch.object(tools.subprocess, 'check_output', return_value='Python/mobile/android/Changed.java\n'), \
                 self.assertRaisesRegex(ValueError, 'compiled source changed'):
                tools.android_shell(receipt, root, root, root, {})
