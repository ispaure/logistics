"""Real VLC prefetch hints, manual pause and rotation acceptance."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback

from mobile.app import LogisticsMobile
from mobile.screen_privacy import native_value
from .rotation_checks import rotate
from .video_probe import until
from .video_ui_probe import player_clock, record


async def exercise(app):
    output = Path(app.paths.cache) / 'video-buffer'
    output.mkdir(exist_ok=True)
    report = dict(success=False, cases=[])
    try:
        startup = getattr(app, 'startup_task', None)
        if startup is not None:
            await asyncio.shield(startup)
        from commonUtils.runtime.resources.local import LocalFiles
        from features.video.mobile.player import open_video
        fixtures = Path(__file__).with_name('video-fixtures')
        for name in ('h264-aac.mp4', 'mpeg4-mp3.avi'):
            assert await open_video(app, LocalFiles(fixtures), name)
            owner = app.video_player
            native = owner.native.native
            await until(lambda: native_value(native.player, 'isPlaying') and player_clock(native.player) > 500)
            token = object()
            owner.network_waiting(token, True)
            clock = player_clock(native.player)
            await asyncio.sleep(2)
            assert player_clock(native.player) > clock + 1000, 'Read-ahead hint interrupted playable data'
            assert not native.networkResumePending and not native.buffering
            native.togglePlay(None)
            assert native.manualResumeRequired
            assert str(native.playButton.accessibilityLabel) == 'Play'
            owner.network_waiting(token, False)
            await until(lambda: not native_value(native.player, 'isPlaying'))
            await asyncio.sleep(.5)
            assert not native_value(native.player, 'isPlaying'), 'Data readiness overrode manual Pause'
            case = dict(file=name, prefetch_does_not_pause=True, manual_pause_preserved=True, rotations=[])
            for orientation in ('portrait', 'landscape-left', 'landscape-right', 'portrait'):
                await rotate(app, orientation)
                await asyncio.sleep(.3)
                case['rotations'].append(await record(app, native, output, name + '-' + orientation))
            report['cases'].append(case)
            await owner.close()
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        owner = getattr(app, 'video_player', None)
        if owner is not None:
            await owner.close()
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print('VIDEO_BUFFER_RESULT=' + json.dumps(report), flush=True)


class VideoBufferProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'video-buffer-private'
        super().startup()

    def on_running(self):
        if getattr(self, '_video_probe_task', None) is None:
            self._video_probe_task = self.loop.create_task(exercise(self))


def main():
    return VideoBufferProbe('Logistics Video QA', 'io.github.ispaure.logisticsmobile')
