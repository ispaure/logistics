"""Native reader packaging requirements are applied idempotently."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import tomllib
import xml.etree.ElementTree as ET
from Mobile.cloud_build import configure_android_appearance, configure_android_sources


class ReaderBuildTests(unittest.TestCase):
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
            config = tomllib.loads((Path(__file__).parents[1] / 'pyproject.toml').read_text())
            code = config['tool']['briefcase']['app']['logisticsmobile']['android']['version_code']
            self.assertIn('versionCode ' + str(code), first)
            self.assertNotIn('versionCode 1\n', first)
            configure_android_sources(root)
            self.assertNotIn('tests.logisticsmobile', metadata.read_text())
            self.assertEqual((root / 'app/extract-packages.txt').read_text(), '')
            self.assertEqual(gradle.read_text(), first)
            self.assertTrue(first.startswith(existing))
            self.assertEqual(first.count('payload/commonUtils/ui/native/android'), 1)
            self.assertEqual(first.count('payload/features/books/mobile/android'), 1)
            self.assertEqual(first.count('payload/logisticsmobile/android'), 1)
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
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><activity android:name="Main" /></application></manifest>'
            )
            configure_android_appearance(root)
            configure_android_appearance(root)
            actions = ET.parse(manifest).getroot().findall("queries/intent/action")
            self.assertEqual(len(actions), 1)
            self.assertEqual(
                actions[0].get("{http://schemas.android.com/apk/res/android}name"),
                "android.intent.action.TTS_SERVICE",
            )

            permissions = ET.parse(manifest).getroot().findall("uses-permission")
            self.assertEqual([item.get("{http://schemas.android.com/apk/res/android}name") for item in permissions],
                             ["android.permission.MANAGE_EXTERNAL_STORAGE", "android.permission.FOREGROUND_SERVICE",
                              "android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK", "android.permission.WAKE_LOCK"])
            services = ET.parse(manifest).getroot().findall("application/service")
            self.assertEqual(len(services), 1)
            namespace = "{http://schemas.android.com/apk/res/android}"
            self.assertEqual(services[0].get(namespace + "exported"), "false")
            self.assertEqual(services[0].get(namespace + "foregroundServiceType"), "mediaPlayback")
