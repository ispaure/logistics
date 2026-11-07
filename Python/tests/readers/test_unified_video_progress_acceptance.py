"""Fresh-process playback options and password-bound progress storage."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from commonUtils.runtime.resources.local import LocalFiles
from features.rclone import session
from features.video.playback import VideoContent
from features.video.session import PlaybackSettings
from services.documents.video_progress import VideoProgress
from services.documents.video_settings import SettingsStore, VideoSettingsStore


VOICE_KEY = '["qa","fra","independent voice","aac"]'
SUBTITLE_KEY = '["qa","eng","independent captions","srt"]'


class ProtectedFiles(LocalFiles):
    """Synthetic decoded source carrying a real desktop ZIP password grant."""

    private = True
    session_only = True
    remote = 'Vault'

    def __init__(self, root, context):
        super().__init__(root)
        self.context = context
        self.storage_namespace = 'qa-localcrypt'


def run_fixture(root, action, password):
    context = root / 'fixture.session'
    if password != '-':
        session.remember(context, {'Vault': dict(type='crypt', password='crypt-key', remote='Memory:fixture'),
                                   'Memory': dict(type='memory')},
                         state_password=password, state_identity='a' * 64)
    try:
        results = {}
        state_root = root / 'app-state' / 'Video'
        defaults = SettingsStore(state_root)
        if action == 'seed':
            defaults.save(asdict(PlaybackSettings(audio_language='eng', subtitle_language='fra',
                                                  subtitle_delay_ms=-100, subtitle_scale=.8)))
        sources = {
            'local': (LocalFiles(root / 'media'), 'Shelf/Film.mkv'),
            'copy': (LocalFiles(root / 'media'), 'Shelf/Copy.mkv'),
            'sidecar': (LocalFiles(root / 'media'), 'Shelf/Sidecar.mkv'),
            'private': (ProtectedFiles(root / 'protected', context), 'Private Film.mkv'),
        }
        if action != 'seed':
            sources['local'] = (LocalFiles(root / 'media/Shelf'), 'Film.mkv')
            sources['sidecar'] = (LocalFiles(root / 'media/Shelf'), 'Sidecar.mkv')
        for key, (provider, name) in sources.items():
            content = VideoContent(provider, name)
            try:
                progress = VideoProgress(content, state_root)
                progress.load()
                store = VideoSettingsStore(progress, state_root)
                options = asdict(store.load())
                if action == 'seed' and key != 'copy':
                    options.update(audio_track=7, audio_track_key=VOICE_KEY,
                                   subtitle_track=5 if key == 'local' else -1,
                                   subtitle_track_key=SUBTITLE_KEY if key == 'local' else '',
                                   subtitle_delay_ms=350, audio_delay_ms=-175, subtitle_scale=1.25,
                                   pip_subtitles=True)
                    if key == 'sidecar':
                        options.update(subtitle_file='Shelf/Sidecar.fra.srt', subtitle_track=None)
                    store.save(options)
                    progress.save(12400)
                elif action == 'locked' and key == 'private':
                    progress.save(6000)
                results[key] = dict(time=progress.position, options=options,
                                    load=progress.state.load_status, mode=progress.state.mode)
                if key == 'sidecar' and action == 'restore':
                    from features.video.sidecars import discover_sidecars

                    subtitles = discover_sidecars(content, preferred=options['subtitle_file'])
                    try:
                        results[key]['sources'] = [item.path for item in subtitles]
                    finally:
                        for item in subtitles:
                            item.close()
                progress.retire()
            finally:
                content.close()
        return results
    finally:
        session.forget(context)


class UnifiedVideoProgressAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        media = self.root / 'media/Shelf'
        media.mkdir(parents=True)
        private = self.root / 'protected'
        private.mkdir()
        # VideoContent samples bounded seekable bytes. The native acceptance
        # probe exercises an actual encoded movie and real decoder selection.
        movie = b'synthetic seekable content' * 300
        for path in (media / 'Film.mkv', media / 'Copy.mkv', media / 'Sidecar.mkv',
                     private / 'Private Film.mkv'):
            path.write_bytes(movie)
        (media / 'Sidecar.fra.srt').write_text(
            '1\n00:00:00,500 --> 00:00:24,000\nSynthetic external captions\n', encoding='utf-8')

    def child(self, action, password='original-password'):
        result = subprocess.run([sys.executable, __file__, action, str(self.root), password],
                                check=True, text=True, capture_output=True, timeout=20)
        return json.loads(result.stdout)

    def test_title_overrides_survive_new_process_and_leave_defaults_for_an_identical_copy(self):
        self.child('seed')
        results = self.child('restore')
        for name, track, track_key, mode in (('local', 5, SUBTITLE_KEY, 'local'),
                                              ('private', -1, '', 'encrypted')):
            with self.subTest(source=name):
                record = results[name]
                self.assertEqual(record['load'], 'restored')
                self.assertEqual(record['mode'], mode)
                self.assertEqual(record['time'], 12400)
                options = record['options']
                self.assertEqual((options['audio_track'], options['audio_track_key']), (7, VOICE_KEY))
                self.assertEqual((options['subtitle_track'], options['subtitle_track_key']), (track, track_key))
                self.assertEqual((options['subtitle_delay_ms'], options['audio_delay_ms'],
                                  options['subtitle_scale'], options['pip_subtitles']), (350, -175, 1.25, True))
        copy = results['copy']
        self.assertEqual(copy['time'], 0)
        self.assertEqual(copy['load'], 'absent')
        self.assertIsNone(copy['options']['audio_track'])
        self.assertIsNone(copy['options']['subtitle_track'])
        self.assertEqual((copy['options']['audio_language'], copy['options']['subtitle_language'],
                          copy['options']['subtitle_delay_ms'], copy['options']['subtitle_scale']),
                         ('eng', 'fra', -100, .8))

    def test_selected_external_subtitle_resolves_through_a_different_browser_root(self):
        self.child('seed')
        sidecar = self.child('restore')['sidecar']
        self.assertEqual(sidecar['time'], 12400)
        self.assertIsNone(sidecar['options']['subtitle_track'])
        self.assertEqual(sidecar['options']['subtitle_file'], 'Shelf/Sidecar.fra.srt')
        self.assertEqual(sidecar['sources'], ['Sidecar.fra.srt'])

    def test_wrong_password_cannot_read_or_replace_encrypted_video_settings(self):
        import pyzipper
        self.child('seed')
        positions = self.root / 'app-state/ReaderPositions'
        record, = positions.glob('*.zip')
        original = record.read_bytes()
        self.assertNotIn(b'Private Film', original)
        self.assertNotIn(VOICE_KEY.encode(), original)
        with pyzipper.AESZipFile(record) as archive:
            archive.setpassword(b'crypt-key')
            with self.assertRaises(RuntimeError):
                archive.read('state.json')
        locked = self.child('locked', 'different-password')['private']
        self.assertEqual(locked['load'], 'locked')
        self.assertIsNone(locked['options']['audio_track'])
        self.assertIsNone(locked['options']['subtitle_track'])
        self.assertEqual(record.read_bytes(), original)
        restored = self.child('restore')['private']
        self.assertEqual((restored['time'], restored['options']['subtitle_track']), (12400, -1))


if __name__ == '__main__':
    action, directory, password = sys.argv[1:]
    print(json.dumps(run_fixture(Path(directory), action, password)))
