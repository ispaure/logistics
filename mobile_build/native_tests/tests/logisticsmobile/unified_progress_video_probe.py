"""Local and LocalCrypt playback state through a full native process restart."""

import asyncio
import base64
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import traceback
from zipfile import ZipFile

from commonUtils.testing.stages import TestStage
from services.documents.mobile_storage import open_provider_document

from .unified_progress_probe import BUNDLE, PASSWORD, RESULT, UnifiedProgressProbe, load_aes_localcrypt_package, write_result
from .video_probe import android_player, until

TEST_STAGE = TestStage.REGRESSION

LOCAL = ('Local captions.mkv', 'Local off.mkv')
PRIVATE = ('Protected captions.mkv', 'Protected off.mkv')
EXTERNAL = 'Local sidecar.mkv'
SIDECAR = 'Local sidecar.fra.srt'
TARGET = 9000
DELAY = 350
AUDIO_DELAY = -175
SCALE = 1.25


def java_field(obj, name):
    field = obj.getClass().getDeclaredField(name)
    field.setAccessible(True)
    return field.get(obj)


class Playback:
    def __init__(self, owner):
        self.owner = owner
        self.controller = owner.native.native
        self.android = type(owner.app._impl).__module__.startswith('toga_android.')
        self.player = android_player(owner) if self.android else self.controller.player

    def tracks(self, subtitles):
        if self.android:
            values = self.player.getSpuTracks() if subtitles else self.player.getAudioTracks()
            return [(int(row.id), row) for row in values or () if row.id >= 0]
        return list(enumerate(self.player.textTracks if subtitles else self.player.audioTracks))

    def key(self, row, subtitles):
        if self.android:
            from java import jarray, jclass
            boolean = jclass('java.lang.Boolean')
            classes = jarray(jclass('java.lang.Class'))([row.getClass(), boolean.TYPE])
            args = jarray(jclass('java.lang.Object'))([row, boolean(subtitles)])
            method = self.controller.getClass().getDeclaredMethod('trackKey', classes)
            method.setAccessible(True)
            return str(method.invoke(self.controller, args))
        return str(self.controller.trackKey(row))

    def selected(self, subtitles):
        tracks = self.tracks(subtitles)
        if self.android:
            selected = self.player.getSpuTrack() if subtitles else self.player.getAudioTrack()
            return [self.key(row, subtitles) for track, row in tracks if track == selected]
        return [self.key(row, subtitles) for _, row in tracks if self.value(row, 'isSelected')]

    @staticmethod
    def value(obj, name):
        from mobile.screen_privacy import native_value
        return native_value(obj, name)

    def clock(self):
        if self.android:
            return int(self.player.getTime())
        value = self.value(self.value(self.player, 'time'), 'value')
        if value is None:
            return 0
        return int(value) if isinstance(value, (int, float)) else int(self.value(value, 'longLongValue'))

    def playing(self):
        return bool(self.value(self.player, 'isPlaying'))

    def ready(self):
        return len(self.tracks(False)) >= 2 and bool(self.tracks(True)) and self.clock() > 0 and self.playing()

    def delays(self):
        if self.android:
            return int(self.player.getSpuDelay()), int(self.player.getAudioDelay())
        return int(self.value(self.player, 'currentVideoSubTitleDelay')), int(self.value(self.player, 'currentAudioPlaybackDelay'))

    def subtitle_size(self):
        if self.android:
            settings = java_field(java_field(self.controller, 'tools'), 'settings')
            return float(settings.getDouble('subtitle_scale'))
        return float(self.value(self.player, 'currentSubTitleFontScale')) * 22 / 20


class VideoRestartProbe(UnifiedProgressProbe):
    async def unlock(self, initial):
        from features.rclone.localcrypt.mobile.resources import encrypted_storage

        self.show_cloud(present=False)
        task = getattr(self, 'cloud_restore_task', None)
        if task is not None:
            await task
        values = dict(package=load_aes_localcrypt_package(), package_name='ProgressFixture.zip', session_only=True)
        if not initial:
            try:
                self.cloud_client.request('import', password='wrong-password', **values)
            except (OSError, ValueError, RuntimeError):
                pass
            else:
                raise AssertionError('Wrong password unlocked the credential fixture')
        self.cloud_client.request('import', password=PASSWORD, **values)
        assert any(not row.get('saved') and row.get('document_cache_id')
                   for row in self.cloud_client.package_records)
        provider = encrypted_storage(self.private_root / 'unified-progress-crypt', self.cloud_client, 'Secret')
        if initial:
            for title in PRIVATE:
                provider.create_file(title, BytesIO(self.fixture.read_bytes()))
        return provider

    @property
    def fixture(self):
        return Path(__file__).with_name('video-fixtures') / 'tracks.mkv'

    async def playback_case(self, name, previous, provider, evidence):
        private = name in PRIVATE
        off = name.endswith('off.mkv')
        external = name == EXTERNAL
        if private:
            assert await open_provider_document(self, provider, name)
        else:
            await self.open_local(name, 'local' if previous is None else 'home')
        owner = self.video_player
        state = owner.progress.state
        evidence.update(mode=state.mode.value, load=state.load_status.value, restricted=owner.restricted)
        assert owner.restricted == private and state.mode == ('encrypted' if private else 'local'), evidence
        playback = Playback(owner)
        play_requested = False

        def ready():
            nonlocal play_requested
            if playback.ready():
                return True
            if (not play_requested and playback.android and self._impl.native.hasWindowFocus()
                    and not playback.playing() and not java_field(playback.controller, 'playRequested')):
                # A cold app can initially miss the automatic Play request
                # before it owns audio focus. Use normal Play once focus arrives.
                play_requested = True
                owner.native.play()
            return False

        try:
            await until(ready, timeout=50 if name == LOCAL[0] else 30)
        except AssertionError as error:
            evidence.update(clock=playback.clock(), playing=playback.playing(), allowed=owner.allowed(),
                            audio=owner.audio_output.permitted(), audio_tracks=len(playback.tracks(False)),
                            subtitle_tracks=len(playback.tracks(True)))
            raise AssertionError(evidence) from error
        voice, captions = playback.tracks(False), playback.tracks(True)
        if previous is None:
            voice_key = playback.key(voice[1][1], False)
            subtitle_key = playback.key(captions[0][1], True)
            assert voice_key != playback.key(voice[0][1], False)
            # The ordinal deliberately points at the other voice. Only the
            # stable selector can restore the intended decoder track.
            updates = dict(audio_track=voice[0][0], audio_track_key=voice_key,
                           subtitle_track=captions[0][0], subtitle_track_key=subtitle_key,
                           subtitle_delay_ms=DELAY, audio_delay_ms=AUDIO_DELAY, subtitle_scale=SCALE)
            if external:
                updates['subtitle_language'] = 'en'
            await owner.controls.command('settings', json.dumps(updates))
            await until(lambda: playback.selected(False) == [voice_key]
                        and playback.selected(True) == [subtitle_key], timeout=15)
            if off:
                await owner.controls.command('settings', '{"subtitle_track":-1,"subtitle_track_key":""}')
            elif external:
                await owner.controls.command('subtitleSelect', SIDECAR)
            # A decoder sample can supersede the settings-only token. The
            # next production checkpoint still contains the selected options.
            await until(lambda: state.write_status == 'saved', timeout=12)
            await until(lambda: playback.value(playback.player, 'isSeekable'))
            owner.native.seek(TARGET)
            target = TARGET
        else:
            target = previous['position']
            voice_key = previous['audio_key']
            subtitle_key = previous['subtitle_key']
            assert state.load_status == 'restored', evidence
        settings = owner.controls.settings
        assert (settings.audio_track_key, settings.subtitle_track_key, settings.subtitle_delay_ms,
                settings.audio_delay_ms, settings.subtitle_scale) == (
                    voice_key, '' if off or external else subtitle_key, DELAY, AUDIO_DELAY, SCALE)
        if off:
            assert settings.subtitle_track == -1
        if external:
            assert settings.subtitle_track is None and Path(settings.subtitle_file).name == SIDECAR

        def subtitle_matches():
            selected = playback.selected(True)
            if external:
                return len(playback.tracks(True)) >= 2 and len(selected) == 1 and selected != [subtitle_key]
            return selected == ([] if off else [subtitle_key])

        await until(lambda: playback.selected(False) == [voice_key] and subtitle_matches(), timeout=12)
        try:
            await until(lambda: abs(playback.clock() - target) <= 1800
                        and abs(owner.progress.position - target) <= 2200, timeout=12)
        except AssertionError as error:
            evidence.update(target=target, clock=playback.clock(), observed=owner.progress.position,
                            playing=playback.playing(), write=state.write_status.value)
            raise AssertionError(evidence) from error
        assert playback.delays() == (DELAY * 1000, AUDIO_DELAY * 1000)
        assert abs(playback.subtitle_size() - SCALE) < .06
        clock = playback.clock()
        await owner.close()
        assert abs(owner.progress.position - clock) <= 2200
        return dict(position=owner.progress.position, decoder=clock, audio_key=voice_key,
                    subtitle_key=subtitle_key, off=off, external=external, subtitle_delay=DELAY, audio_delay=AUDIO_DELAY, scale=SCALE)

    def audit(self, cases):
        positions = self.private_root / 'ReaderPositions'
        records = sorted(positions.glob('*.zip'))
        assert len(records) == len(PRIVATE), [path.name for path in records]
        verified = set()
        for path in records:
            raw = path.read_bytes()
            assert len(path.stem) == 64
            with ZipFile(BytesIO(raw)) as archive:
                record, = archive.infolist()
                assert record.flag_bits & 1 and record.compress_type == 99
                assert b'\x01\x99\x07\x00\x02\x00AE\x03' in record.extra
            with path.open('rb') as stream:
                try:
                    self.cloud_client.request('file_archive', fd=stream.fileno(), password='wrong-password',
                                              member=record.filename)
                except (OSError, ValueError, RuntimeError):
                    pass
                else:
                    raise AssertionError('Wrong password decrypted a video checkpoint')
            with path.open('rb') as stream:
                reply = self.cloud_client.request('file_archive', fd=stream.fileno(), password=PASSWORD,
                                                  member=record.filename)
            envelope = json.loads(base64.b64decode(reply['data'], validate=True))
            assert envelope['kind'] == 'video'
            locator = envelope['state']
            settings = locator['settings']
            off = settings.get('subtitle_track') == -1
            title = PRIVATE[int(off)]
            expected = cases[title]
            assert title not in verified and 'error' not in expected
            assert abs(locator['position'] - expected['position']) <= 2200
            assert settings['audio_track_key'] == expected['audio_key']
            assert settings['subtitle_track_key'] == ('' if off else expected['subtitle_key'])
            assert (settings['subtitle_delay_ms'], settings['audio_delay_ms'], settings['subtitle_scale']) == (
                DELAY, AUDIO_DELAY, SCALE)
            for marker in (title.encode(), expected['audio_key'].encode(), b'subtitle_delay_ms'):
                assert marker not in raw
            verified.add(title)
        for path in positions.rglob('*.json'):
            assert all(title.encode() not in path.read_bytes() for title in PRIVATE)
        assert verified == set(PRIVATE)
        return dict(aes_256=True, wrong_password_rejected=True, records=len(verified),
                    ciphertext_sha256=[sha256(path.read_bytes()).hexdigest() for path in records])

    def set_android_subtitle_default(self, value):
        from dataclasses import asdict, replace
        from services.documents.video_settings import SettingsStore

        defaults = SettingsStore(Path(self.private_root) / 'Video')
        defaults.save(asdict(replace(defaults.load(), subtitle_scale=value)))

    async def probe(self):
        cache = Path(self.paths.cache)
        checkpoint = cache / 'video-restart-checkpoint.json'
        previous = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
        initial = previous is None
        cases, evidence = {}, {}
        result = dict(success=False, phase='checkpoint' if initial else 'restarted',
                      pid=os.getpid(), cases=cases, evidence=evidence)
        try:
            await until(lambda: not getattr(self, '_startup_in_progress', False), timeout=60)
            self.preferences.save(restore_last_document='false', clear_unmodified_documents_on_restart='false')
            android = type(self._impl).__module__.startswith('toga_android.')
            local = LOCAL if android else (*LOCAL, EXTERNAL)
            if initial and android:
                self.set_android_subtitle_default(SCALE)
            if initial:
                self.shelf.mkdir(parents=True, exist_ok=True)
                for name in local:
                    shutil.copyfile(self.fixture, self.shelf / name)
                if not android:
                    (self.shelf / SIDECAR).write_text(
                        '1\n00:00:00,500 --> 00:00:26,000\nSynthetic external captions\n', encoding='utf-8')
            else:
                assert previous['pid'] != os.getpid()
            provider = None
            for name in (*local, *PRIVATE):
                evidence[name] = {}
                try:
                    async with asyncio.timeout(105 if name == LOCAL[0] else 55):
                        if name in PRIVATE and provider is None:
                            provider = await self.unlock(initial)
                        prior = None if initial else previous['cases'][name]
                        assert prior is None or 'error' not in prior, 'Initial process did not establish playback'
                        cases[name] = await self.playback_case(name, prior, provider, evidence[name])
                except Exception:
                    cases[name] = dict(error=traceback.format_exc())
                    player = getattr(self, 'video_player', None)
                    if player is not None:
                        await player.close()
            try:
                cases['LocalCrypt encryption'] = self.audit(cases)
            except Exception:
                cases['LocalCrypt encryption'] = dict(error=traceback.format_exc())
            if initial:
                if android:
                    self.set_android_subtitle_default(1.0)
                write_result(checkpoint, result)
            result['success'] = initial or all(
                'error' not in row for phase in (previous['cases'], cases) for row in phase.values())
            if not result['success']:
                result['error'] = 'A native video restart assertion failed. See case evidence.'
        except Exception:
            result['error'] = traceback.format_exc()
        write_result(cache / RESULT, result)


def main():
    return VideoRestartProbe('Unified Progress Video QA', BUNDLE)
