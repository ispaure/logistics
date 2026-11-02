"""Installed dependency closure and offline notice integrity."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import tomllib
from unittest.mock import patch

from services.open_source import bundled_notices, desktop_native_notices, installed_notices, python_notices, runtime_requirements

ROOT = Path(__file__).resolve().parents[2]


class OpenSourceTests(unittest.TestCase):
    def test_native_catalog_matches_pinned_direct_dependencies(self):
        entries = json.loads((ROOT / 'services/licenses/native.json').read_text())
        android = {entry['module'] + ':' + entry['version'] for entry in entries if 'module' in entry}
        config = tomllib.loads((ROOT.parent / 'mobile_build/pyproject.toml').read_text())
        self.assertEqual(android, set(config['tool']['briefcase']['app']['logisticsmobile']['android']['build_gradle_dependencies']))
        from mobile_build.build_support.video_build import VLC_REVISION
        self.assertEqual(next(entry['version'] for entry in entries if entry['name'] == 'VLCKit'), VLC_REVISION)
        rclone = next(entry for entry in entries if entry['name'] == 'rclone')
        desktop = json.loads((ROOT / 'software_manifest.json').read_text())['rclone']
        self.assertEqual({item['version'] for item in desktop.values()}, {rclone['version']})
        dependencies = json.loads((ROOT / 'services/licenses/rclone-dependency-notices.json').read_text())
        self.assertEqual(dependencies['version'], rclone['version'])
        self.assertIn('github.com/rclone/rclone', {item['name'] for item in dependencies['components']})

    def test_qt_notice_versions_match_the_installed_frameworks(self):
        from importlib.metadata import version
        from PySide6.QtWebEngineCore import qWebEngineVersion
        resources = ROOT / 'services/licenses'
        source = json.loads((resources / 'qt-source-notices.json').read_text())
        engine = json.loads((resources / 'qtwebengine-source-notices.json').read_text())
        self.assertEqual(source['version'], version('PySide6'))
        self.assertEqual(engine['version'], qWebEngineVersion())
        self.assertIn('qtquick3d', source['modules'])
        self.assertTrue(any(item['name'] == 'PDFium' for item in engine['components']))
        self.assertTrue(all(item['text'] for item in engine['components']))

    def test_desktop_downloaded_vlc_notices_are_read_without_installing(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(desktop_native_notices(root), [])
            self.assertFalse((root / 'video').exists())
            notices = root / 'video/libvlc-mac-1-arm64/notices'
            notices.mkdir(parents=True)
            (notices / 'COPYING.txt').write_text('Full decoder license')
            (notices / 'third-party').mkdir()
            (notices / 'third-party/COPYING').write_text('Nested codec notice')
            items = desktop_native_notices(root)
            self.assertEqual(len(items), 1)
            self.assertIn('Full decoder license', items[0].content)
            self.assertIn('Nested codec notice', items[0].content)

    def test_installed_dependency_closure_keeps_notices_and_excludes_optional_extras(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'LICENSE').write_text('Full upstream notice')
            packages = {
                'parent': SimpleNamespace(metadata={'Name': 'Parent', 'License': 'MIT'}, version='1',
                    requires=['child; python_version >= "3.0"', 'optional; extra == "dev"'],
                    files=[Path('LICENSE')], locate_file=lambda file: root / file),
                'child': SimpleNamespace(metadata={'Name': 'Child', 'License': 'BSD-3-Clause'}, version='2',
                    requires=['parent'], files=[], locate_file=lambda file: root / file),
            }
            # Metadata normally exposes get_all in addition to mapping access.
            class Info(dict):
                def get_all(self, key):
                    return []
            for item in packages.values():
                item.metadata = Info(item.metadata)
            with patch('services.open_source.metadata.distribution', side_effect=packages.__getitem__) as lookup:
                notices = python_notices(['parent'])
            self.assertEqual({notice.name for notice in notices}, {'Parent', 'Child'})
            self.assertIn('Full upstream notice', notices[0].content)
            self.assertIn('No complete license text', next(item.text for item in notices if item.name == 'Child'))
            self.assertEqual(lookup.call_count, 2)

    def test_explicit_extras_are_followed_without_listing_unrelated_extras(self):
        from email.message import Message
        def distribution(name, requires):
            info = Message()
            info['Name'] = name
            info['License'] = 'MIT'
            return SimpleNamespace(metadata=info, version='1', files=[], requires=requires)
        packages = {'parent': distribution('parent', ['child; extra == "reader"', 'unused; extra == "dev"']),
                    'child': distribution('child', [])}
        with patch('services.open_source.metadata.distribution', side_effect=packages.__getitem__):
            notices = python_notices(['parent[reader]'])
        self.assertEqual({item.name for item in notices}, {'parent', 'child'})

    def test_python_wheel_license_files_can_be_read_without_record(self):
        from email.message import Message
        info = Message()
        info['Name'] = 'example'
        info['License-File'] = 'licenses/LEGAL.txt'
        package = SimpleNamespace(metadata=info, version='1', files=None, requires=[],
            read_text=lambda name: 'Full installed publisher license' if name == 'licenses/LEGAL.txt' else None)
        with patch('services.open_source.metadata.distribution', return_value=package):
            notice = python_notices(['example'])[0]
        self.assertIn('Full installed publisher license', notice.text)

    def test_resolved_android_inventory_replaces_static_direct_entry(self):
        inventory = dict(components=[dict(module='androidx.appcompat:appcompat', name='AndroidX AppCompat',
            version='1.7.1', text='Selected artifact notice', license='Apache-2.0')])
        notices = bundled_notices(ROOT, 'android', inventory)
        entries = [item for item in notices if item.name == 'AndroidX AppCompat']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].version, '1.7.1')
        self.assertEqual(entries[0].text, 'Selected artifact notice')

    def test_platforms_only_show_their_native_components_and_texts_exist(self):
        android = bundled_notices(ROOT, 'android')
        ios = bundled_notices(ROOT, 'ios')
        self.assertIn('LibVLC Android', {notice.name for notice in android})
        self.assertNotIn('VLCKit', {notice.name for notice in android})
        self.assertIn('VLCKit', {notice.name for notice in ios})
        self.assertNotIn('Onyx pen SDK', {notice.name for notice in ios})
        self.assertIn('Rick Lupton', next(item.text for item in ios if item.name == 'rmscene'))
        for platform in ('darwin', 'win32', 'linux'):
            rclone = next(item for item in bundled_notices(ROOT, platform) if item.name == 'rclone')
            self.assertEqual(rclone.license, 'MIT')
            self.assertIn('Nick Craig-Wood', rclone.text)
        self.assertNotIn('rclone', {item.name for item in ios})
        for entry in json.loads((ROOT / 'services/licenses/native.json').read_text()):
            for name in entry.get('files', ()):
                self.assertGreater((ROOT / 'services/licenses' / name).stat().st_size, 1000)

    def test_go_manifest_preserves_module_notice_and_runtime_license(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            native = root / 'mobile/native-licenses'
            native.mkdir(parents=True)
            (native / 'module-LICENSE').write_text('Upstream Go module notice')
            (native / 'Go-LICENSE').write_text('Go copyright')
            (native / 'manifest.json').write_text(json.dumps([
                dict(module='github.com/rclone/rclone', version='v1.74.1', notices=[dict(file='module-LICENSE')])]))
            notices = bundled_notices(root, 'ios')
            rclone = next(item for item in notices if item.name == 'github.com/rclone/rclone')
            self.assertEqual(rclone.version, 'v1.74.1')
            self.assertIn('Upstream Go module notice', rclone.text)
            self.assertIn('Go copyright', next(item.text for item in notices if item.name == 'Go runtime'))

    def test_staged_runtime_does_not_need_repository_or_network(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'mobile').mkdir()
            (root / 'mobile/open-source-dependencies.json').write_text(json.dumps({'ios': ['toga-iOS'], 'android': ['toga-android']}))
            self.assertEqual(runtime_requirements(root, 'ios'), ['toga-iOS'])
            with patch('services.open_source.python_notices', return_value=[]) as python:
                installed_notices(root=root, platform='android')
            python.assert_called_once_with(['toga-android'])
