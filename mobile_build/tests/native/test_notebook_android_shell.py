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
    def test_fresh_palm_package_evidence_survives_owned_build_cleanup(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            work, output = root / 'work', root / 'evidence'
            native = work / 'payload/features/notebooks/mobile/android'
            native.mkdir(parents=True)
            (native / 'NotebookInput.java').write_text('synthetic source')
            shared = work / 'payload/commonUtils/ui/native/android/io/github/ispaure/commonutils'
            shared.mkdir(parents=True)
            (shared / 'ImageCanvasView.java').write_text('synthetic shared source')
            classes = work / 'build/classes'
            classes.mkdir(parents=True)
            (classes / 'NotebookInput.class').write_bytes(b'synthetic class')
            (classes / 'ImageCanvasView$PageListener.class').write_bytes(b'synthetic tap listener')
            apk = work / 'built.apk'
            with ZipFile(apk, 'w') as archive:
                archive.writestr('classes.dex', b'synthetic DEX')
            output.mkdir()
            digest = sha256(apk.read_bytes()).hexdigest()
            (output / 'android-apk.json').write_text(json.dumps(dict(apk=str(apk), sha256=digest)))
            (output / 'source.json').write_text(json.dumps(dict(logistics_commit='frozen')))
            tools.retain_palm_package(work, output)
            saved = output / 'notebook-palm.apk'
            try:
                apk.unlink()
                receipt = json.loads((output / 'android-shell.json').read_text())
                self.assertEqual(sha256(saved.read_bytes()).hexdigest(), digest)
                self.assertEqual(receipt['source']['logistics_commit'], 'frozen')
                self.assertIn('build/classes/NotebookInput.class', receipt['native_class_hashes'])
                self.assertIn('NotebookInput.java', receipt['native_source_hashes'])
                self.assertEqual(receipt['compiled_payload'], tools.compiled_payload(saved))
                self.assertTrue(receipt['read_only'])
                self.assertIn('build/classes/ImageCanvasView$PageListener.class', receipt['native_class_hashes'])
                self.assertIn('commonUtils/io/github/ispaure/commonutils/ImageCanvasView.java', receipt['native_source_hashes'])
                # The same manager-owned package can retain a link-specific immutable receipt.
                apk.write_bytes(saved.read_bytes())
                tools.retain_palm_package(work, output, name='links')
                link_package = output / 'notebook-links.apk'
                try:
                    link_receipt = json.loads((output / 'android-shell.json').read_text())
                    self.assertEqual(link_receipt['apk'], str(link_package))
                    self.assertEqual(link_receipt['sha256'], digest)
                finally:
                    link_package.chmod(0o644)
            finally:
                saved.chmod(0o644)

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
