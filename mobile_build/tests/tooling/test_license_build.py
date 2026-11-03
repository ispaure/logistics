"""Resolved native artifact versions, notices and generated assets."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from mobile_build.build_support import license_build
from mobile_build import cloud_build

RESOURCES = Path(__file__).resolve().parents[3] / 'Python/services/licenses'


class LicenseBuildTests(unittest.TestCase):
    def test_runtime_own_license_is_retained_alongside_vendored_notices(self):
        with TemporaryDirectory() as temporary:
            artifact = Path(temporary) / 'bootstrap.jar'
            with ZipFile(artifact, 'w') as archive:
                archive.writestr('vendor/NOTICE', 'Vendored library attribution')
            data = license_build.collect_android({'artifacts': [dict(module='com.chaquo.python.runtime:bootstrap',
                version='17.0.0', file=str(artifact))]}, RESOURCES)
            text = data['components'][0]['text']
            self.assertIn('Vendored library attribution', text)
            self.assertIn('Chaquo Ltd and contributors', text)

    def test_selected_version_and_nested_notice_replace_declared_version(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            jar = BytesIO()
            with ZipFile(jar, 'w') as archive:
                archive.writestr('META-INF/LICENSE', 'Actual artifact copyright and license')
            artifact = root / 'device.aar'
            with ZipFile(artifact, 'w') as archive:
                archive.writestr('classes.jar', jar.getvalue())
            data = license_build.collect_android({'artifacts': [dict(module='androidx.appcompat:appcompat', version='1.7.1', file=str(artifact))]}, RESOURCES)
            item = data['components'][0]
            self.assertEqual(item['version'], '1.7.1')
            self.assertIn('Actual artifact copyright and license', item['text'])
            self.assertFalse(item['missing_notice'])

    def test_onyx_declarations_and_demo_license_do_not_clear_missing_sdk_notices(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / 'sdk.aar'
            with ZipFile(artifact, 'w') as archive:
                # Even an incidental generic license must not silently clear the
                # explicitly reviewed missing publisher copyright notice.
                archive.writestr('LICENSE', (RESOURCES / 'Apache-2.0.txt').read_text())
            records = [dict(module='com.onyx.android.sdk:onyxsdk-pen', version='1.5.8', file=str(artifact)),
                       dict(module='com.onyx.android.sdk:onyxsdk-pennative', version='1.0.5', file=str(artifact))]
            data = license_build.collect_android({'artifacts': records}, RESOURCES)
            entries = {item['module']: item for item in data['components']}
            pen = entries['com.onyx.android.sdk:onyxsdk-pen']
            native = entries['com.onyx.android.sdk:onyxsdk-pennative']
            self.assertIn('BSD-3-Clause', pen['license'])
            self.assertEqual(native['license'], 'Not declared by publisher')
            self.assertTrue(pen['missing_notice'])
            self.assertTrue(native['missing_notice'])

    def test_google_terms_are_offline_and_duplicate_artifacts_are_merged(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / 'library.jar'
            with ZipFile(artifact, 'w') as archive:
                archive.writestr('Class.class', b'class')
            pom = root / 'library.pom'
            pom.write_text('<project><licenses><license><name>Android Software Development Kit License</name></license></licenses></project>')
            item = dict(module='com.google.android.gms:example', version='1', file=str(artifact), pom=str(pom))
            result = license_build.collect_android({'artifacts': [item, item]}, RESOURCES)['components']
            self.assertEqual(len(result), 1)
            self.assertIn('Android Software Development Kit License Agreement', result[0]['text'])
            self.assertFalse(result[0]['missing_notice'])

    def test_go_collector_unions_architectures_and_preserves_colliding_basenames(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = root / 'module'
            package = module / 'nested'
            package.mkdir(parents=True)
            (module / 'LICENSE').write_text('Root license')
            (package / 'LICENSE').write_text('Nested license')
            go = root / 'go'
            go.mkdir()
            (go / 'LICENSE').write_text('Go license')
            record = json.dumps(dict(Module=dict(Path='example.org/module', Version='v1', Dir=str(module)), Dir=str(package)))
            with patch.object(cloud_build.subprocess, 'check_output', side_effect=[record, record, str(go)]) as command:
                output = root / 'notices'
                cloud_build.licenses(output, platform='android')
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(len(manifest), 1)
            notices = manifest[0]['notices']
            self.assertEqual({item['path'] for item in notices}, {'LICENSE', 'nested/LICENSE'})
            self.assertEqual(len({item['file'] for item in notices}), 2)
            self.assertEqual([call.kwargs['env']['GOARCH'] for call in command.call_args_list[:2]], ['arm64', 'amd64'])
            self.assertTrue(all(call.kwargs['env']['GOOS'] == 'android' for call in command.call_args_list[:2]))

    def test_generated_assets_are_wired_to_current_android_variant_api(self):
        with TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / 'app').mkdir()
            gradle = project / 'app/build.gradle'
            gradle.write_text('// fixture\n')
            license_build.configure_android(project, '/example/python')
            license_build.configure_android(project, '/example/python')
            self.assertEqual(gradle.read_text().count('apply from:'), 1)
            script = (project / 'app/logistics-license-tools/android_licenses.gradle').read_text()
            self.assertIn('addGeneratedSourceDirectory', script)
            self.assertIn('RuntimeClasspath', script)
            self.assertFalse((project / 'app/logistics-license-tools/licenses/qt-source-notices.json').exists())
