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

    def test_desktop_downloaded_vlc_notices_are_read_without_installing(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(desktop_native_notices(root), [])
            self.assertFalse((root / 'video').exists())
            notices = root / 'video/libvlc-mac-1-arm64/notices'
            notices.mkdir(parents=True)
            (notices / 'COPYING.txt').write_text('Full decoder license')
            items = desktop_native_notices(root)
            self.assertEqual(len(items), 1)
            self.assertIn('Full decoder license', items[0].content)

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

    def test_platforms_only_show_their_native_components_and_texts_exist(self):
        android = bundled_notices(ROOT, 'android')
        ios = bundled_notices(ROOT, 'ios')
        self.assertIn('LibVLC Android', {notice.name for notice in android})
        self.assertNotIn('VLCKit', {notice.name for notice in android})
        self.assertIn('VLCKit', {notice.name for notice in ios})
        self.assertNotIn('Onyx pen SDK', {notice.name for notice in ios})
        self.assertIn('Rick Lupton', next(item.text for item in ios if item.name == 'rmscene'))
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
                dict(module='example.org/module', version='v1', notices=[dict(file='module-LICENSE')])]))
            notices = bundled_notices(root, 'ios')
            self.assertIn('Upstream Go module notice', next(item.text for item in notices if item.name == 'example.org/module'))
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
