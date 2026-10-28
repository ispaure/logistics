"""Native reader packaging requirements are applied idempotently."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import tomllib
import xml.etree.ElementTree as ET
from mobile_build.cloud_build import configure_android_appearance, configure_android_sources


class ReaderBuildTests(unittest.TestCase):
    @patch.dict('os.environ', PIP_FIND_LINKS='"/tmp/wheels with spaces"')
    def test_existing_android_project_gains_speech_java_sources(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            gradle = root / 'app/build.gradle'
            gradle.parent.mkdir()
            existing = ('plugins { id "com.android.application" }\n'
                'android.sourceSets.main.java.srcDir(new File(rootProject.projectDir, '
                '"../../../../payload/commonUtils/ui/native/android"))\n')
            gradle.write_text(existing + 'android {\n    defaultConfig {\n        versionCode 1\n    }\n}\n')
            configure_android_sources(root)
            self.assertEqual((root / 'app/extract-packages.txt').read_text(), '')
            metadata = root / 'app/src/main/res/values/briefcase.xml'
            self.assertIn('>logisticsmobile<', metadata.read_text())
            metadata.write_text('<resources><string name="main_module">tests.logisticsmobile</string></resources>')
            (root / 'app/extract-packages.txt').write_text('tests')
            first = gradle.read_text()
            config = tomllib.loads((Path(__file__).parents[2] / 'pyproject.toml').read_text())
            code = config['tool']['briefcase']['app']['logisticsmobile']['android']['version_code']
            self.assertIn('versionCode ' + str(code), first)
            self.assertNotIn('versionCode 1\n', first)
            configure_android_sources(root)
            self.assertNotIn('tests.logisticsmobile', metadata.read_text())
            self.assertEqual((root / 'app/extract-packages.txt').read_text(), '')
            self.assertEqual(gradle.read_text(), first)
            self.assertEqual((root / 'app/pip-options.txt').read_text(),
                             '--find-links=/tmp/wheels with spaces\n')
            self.assertTrue(first.startswith(existing))
            self.assertEqual(first.count('payload/commonUtils/ui/native/android'), 1)
            self.assertEqual(first.count('payload/features/books/mobile/android'), 1)
            self.assertEqual(first.count('payload/mobile/android'), 1)
            self.assertEqual(first.count('payload/features/notebooks/mobile/android'), 1)
            self.assertEqual(first.count('com.onyx.android.sdk:onyxsdk-device:1.3.5.3'), 1)
            self.assertEqual(first.count('com.onyx.android.sdk:onyxsdk-pen:1.5.8'), 1)
            self.assertEqual(first.count('configurations.configureEach { exclude group: "com.android.support" }'), 1)
            self.assertEqual(first.count('pickFirst "lib/*/libc++_shared.so"'), 1)
            self.assertEqual((root / 'gradle.properties').read_text().count('android.enableJetifier=true'), 1)
            self.assertEqual(first.count('org.lsposed.hiddenapibypass:hiddenapibypass:4.3'), 1)
            self.assertEqual(first.count('https://repo.boox.com/repository/maven-public/'), 1)
            menu = root / 'app/src/main/res/drawable/logistics_menu.xml'
            contrast = root / 'app/src/main/res/drawable/logistics_menu_contrast.xml'
            namespace = '{http://schemas.android.com/apk/res/android}'
            self.assertEqual(ET.parse(menu).getroot().find('corners').get(namespace + 'radius'), '8dp')
            outline = ET.parse(contrast).getroot().find('stroke')
            self.assertEqual(outline.get(namespace + 'width'), '1dp')
            self.assertEqual(outline.get(namespace + 'color'), '#000000')
            self.assertTrue((root / 'app/src/main/res/values-night/menus.xml').is_file())
            for name in ('back15', 'forward15'):
                icon = root / ('app/src/main/res/drawable/speech_' + name + '.xml')
                self.assertEqual(ET.parse(icon).getroot().tag, 'vector')
                self.assertTrue(ET.parse(icon).getroot().find('path').attrib)


    def test_android_speech_service_visibility_survives_repeated_configuration(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            styles = root / "app/src/main/res/values/styles.xml"
            styles.parent.mkdir(parents=True)
            styles.write_text(
                '<resources><style name="AppTheme" parent="Theme.AppCompat.Light.DarkActionBar" /></resources>'
            )
            manifest = root / "app/src/main/AndroidManifest.xml"
            manifest.write_text(
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application android:label="@string/formal_name"><activity android:name="Main" /></application></manifest>'
            )
            configure_android_appearance(root)
            configure_android_appearance(root)
            application = ET.parse(manifest).getroot().find('application')
            self.assertEqual(application.get('{http://schemas.android.com/tools}replace'), 'android:label')
            self.assertEqual(application.get('{http://schemas.android.com/apk/res/android}label'), '@string/formal_name')
            actions = ET.parse(manifest).getroot().findall("queries/intent/action")
            self.assertEqual(len(actions), 1)
            self.assertEqual(
                actions[0].get("{http://schemas.android.com/apk/res/android}name"),
                "android.intent.action.TTS_SERVICE",
            )

            permissions = ET.parse(manifest).getroot().findall("uses-permission")
            removed = [item for item in permissions if item.get('{http://schemas.android.com/tools}node') == 'remove']
            self.assertEqual({item.get('{http://schemas.android.com/apk/res/android}name') for item in removed},
                             {'android.permission.' + name for name in ('CHANGE_WIFI_STATE', 'BLUETOOTH', 'DUMP')})
            self.assertEqual([item.get("{http://schemas.android.com/apk/res/android}name") for item in permissions if item not in removed],
                             ["android.permission.MANAGE_EXTERNAL_STORAGE", "android.permission.FOREGROUND_SERVICE",
                              "android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK", "android.permission.WAKE_LOCK",
                              "android.permission.ACCESS_WIFI_STATE", "android.permission.ACCESS_COARSE_LOCATION",
                              "android.permission.ACCESS_FINE_LOCATION"])
            services = ET.parse(manifest).getroot().findall("application/service")
            self.assertEqual(len(services), 1)
            namespace = "{http://schemas.android.com/apk/res/android}"
            self.assertEqual(services[0].get(namespace + "exported"), "false")
            self.assertEqual(services[0].get(namespace + "foregroundServiceType"), "mediaPlayback")
