"""Native reader packaging requirements are applied idempotently."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET
from Mobile.cloud_build import configure_android_appearance


class ReaderBuildTests(unittest.TestCase):
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
                             ["android.permission.MANAGE_EXTERNAL_STORAGE"])
