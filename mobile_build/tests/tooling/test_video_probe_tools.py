"""Archive restaging must test current code rather than stale compiled payloads."""
from hashlib import sha1
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from mobile_build.validation.video_probe_tools import prepare


class VideoProbeRestagingTests(unittest.TestCase):
    def test_cloud_probe_replaces_old_feature_bytecode_and_keeps_native_binary(self):
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            contents = BytesIO()
            with ZipFile(contents, 'w') as app:
                for name in ('features/media/playback.pyc', 'features/video/playback.pyc',
                             'logisticsmobile/__main__.pyc', 'tests/logisticsmobile/__main__.pyc'):
                    app.writestr(name, b'stale payload')
            original = workspace / 'base.apk'
            with ZipFile(original, 'w') as apk:
                apk.writestr('assets/chaquopy/app.imy', contents.getvalue())
                apk.writestr('assets/chaquopy/build.json', json.dumps(dict(assets={'app.imy': 'old'})))
                apk.writestr('classes.dex', b'Lio/github/ispaure/logistics/video/VideoPlayer$Listener;')
                apk.writestr('lib/arm64-v8a/libvlc.so', b'unchanged native decoder')
            fixture = workspace / 'fixtures'
            fixture.mkdir()
            (fixture / 'sentinel.mp4').write_bytes(b'fixture')

            def stage(root, destination, **options):
                (destination / 'features/video').mkdir(parents=True)
                (destination / 'features/video/playback.py').write_text('CURRENT = True\n')
                (destination / 'logisticsmobile').mkdir()
                (destination / 'logisticsmobile/__main__.py').write_text('production entrypoint')
                (destination / 'source.json').write_text('{"fingerprint": "current"}')

            with patch('mobile_build.validation.video_probe_tools.stage', side_effect=stage), patch(
                    'mobile_build.validation.video_probe_tools.cloud_fixtures', return_value=fixture):
                unsigned = prepare(original, workspace, cloud=True)
            with ZipFile(unsigned) as apk:
                self.assertEqual(apk.read('lib/arm64-v8a/libvlc.so'), b'unchanged native decoder')
                raw = apk.read('assets/chaquopy/app.imy')
                self.assertEqual(json.loads(apk.read('assets/chaquopy/build.json'))['assets']['app.imy'], sha1(raw).hexdigest())
                self.assertNotIn('lib/arm64-v8a/wrap.sh', apk.namelist())
                with ZipFile(BytesIO(raw)) as app:
                    self.assertEqual(app.read('features/video/playback.py'), b'CURRENT = True\n')
                    self.assertNotIn('features/media/playback.pyc', app.namelist())
                    self.assertNotIn('features/video/playback.pyc', app.namelist())
                    self.assertNotIn('logisticsmobile/__main__.pyc', app.namelist())
                    self.assertIn(b'video_cloud_probe', app.read('logisticsmobile/__main__.py'))
                    self.assertIn('tests/logisticsmobile/video_webdav.py', app.namelist())
