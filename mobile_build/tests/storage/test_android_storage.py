"""Storage discovery against strict old/new Android API surfaces."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mobile.storage_ui import android_drives, all_files_allowed


class Directory:
    def __init__(self, path, state='mounted'):
        self.path, self.state = path, state

    def getAbsolutePath(self):
        return self.path


class AndroidStorageTests(unittest.TestCase):
    def java(self, sdk, **classes):
        available = {'android.os.Build$VERSION': SimpleNamespace(SDK_INT=sdk), **classes}
        # Unknown classes and unavailable methods deliberately fail: an old
        # device must never reach API 30 volume methods or permission settings.
        return patch.dict(sys.modules, {'java': SimpleNamespace(jclass=available.__getitem__)})

    def test_legacy_discovers_app_directories_and_skips_unavailable_cards(self):
        primary = Directory('/storage/emulated/0/Android/data/io.github.ispaure.logisticsmobile/files')
        card = Directory('/storage/1234-5678/Android/data/io.github.ispaure.logisticsmobile/files')
        readonly = Directory('/storage/READ-ONLY/Android/data/io.github.ispaure.logisticsmobile/files', 'mounted_ro')
        unknown = Directory('/storage/UNKNOWN/Android/data/io.github.ispaure.logisticsmobile/files')
        labels = {primary.path: 'Device', card.path: 'SD card'}
        manager = SimpleNamespace(getStorageVolume=lambda directory: (
            SimpleNamespace(getDescription=lambda context: labels[directory.path]) if directory.path in labels else None))
        native = SimpleNamespace(getSystemService=lambda service: manager,
                                 getExternalFilesDirs=lambda kind: [primary, None, card, readonly, unknown])
        app = SimpleNamespace(_impl=SimpleNamespace(native=native))
        for sdk in (24, 28, 29):
            with self.subTest(sdk=sdk), self.java(sdk, **{
                'android.content.Context': SimpleNamespace(STORAGE_SERVICE='storage'),
                'android.os.Environment': SimpleNamespace(getExternalStorageState=lambda directory: directory.state),
            }):
                drives = android_drives(app)
            self.assertEqual(list(drives.values()), [None, Path(primary.path), Path(card.path)])
            self.assertIn('SD card · app storage', list(drives)[2])

    def test_legacy_without_mounted_external_storage_keeps_internal_choice(self):
        native = SimpleNamespace(getSystemService=lambda service: SimpleNamespace(),
                                 getExternalFilesDirs=lambda kind: [None])
        with self.java(28, **{'android.content.Context': SimpleNamespace(STORAGE_SERVICE='storage'),
                              'android.os.Environment': SimpleNamespace()}):
            self.assertEqual(android_drives(SimpleNamespace(_impl=SimpleNamespace(native=native))),
                             {'App internal storage': None})

    def test_modern_discovers_mounted_volume_roots(self):
        volumes = [SimpleNamespace(getDirectory=lambda: Directory('/storage/1234-5678'),
                                   getState=lambda: 'mounted', getDescription=lambda context: 'SD card'),
                   SimpleNamespace(getDirectory=lambda: None, getState=lambda: 'removed')]
        manager = SimpleNamespace(getStorageVolumes=lambda: SimpleNamespace(size=lambda: len(volumes),
                                                                            get=volumes.__getitem__))
        app = SimpleNamespace(_impl=SimpleNamespace(native=SimpleNamespace(getSystemService=lambda service: manager)))
        for sdk in (30, 35):
            with self.subTest(sdk=sdk), self.java(sdk, **{
                'android.content.Context': SimpleNamespace(STORAGE_SERVICE='storage'),
            }):
                self.assertEqual(android_drives(app), {'App internal storage': None,
                                 'SD card · /storage/1234-5678': Path('/storage/1234-5678')})

    def test_legacy_app_directories_need_no_all_files_api(self):
        for sdk in (24, 28, 29):
            with self.subTest(sdk=sdk), self.java(sdk):
                self.assertTrue(all_files_allowed())

    def test_modern_storage_still_requires_the_all_files_grant(self):
        for sdk in (30, 35):
            for granted in (False, True):
                with self.subTest(sdk=sdk, granted=granted), self.java(sdk, **{
                    'android.os.Environment': SimpleNamespace(isExternalStorageManager=lambda: granted),
                }):
                    self.assertEqual(all_files_allowed(), granted)
