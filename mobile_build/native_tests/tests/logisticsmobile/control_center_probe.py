"""Real iOS decoder with injected foreground interruption/background notifications."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4
from mobile.app import LogisticsMobile
from mobile.screen_privacy import native_value
from services.session_auth import ResumePassword
from commonUtils.runtime.resources.local import LocalFiles
from features.video.mobile.player import open_video
from . import start_native_check
from .video_probe import until


class ControlCenterProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('control-center-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def probe(self):
        report = dict(success=False, cases=[], injected_notifications=True)
        release = None
        try:
            from rubicon.objc import ObjCClass
            center = ObjCClass('NSNotificationCenter').defaultCenter
            def post(name):
                center.postNotificationName(name, object=None)
            for protected in (False, True):
                gate = ResumePassword('synthetic-password')
                if protected:
                    release = self.protection.register(object(), lambda: (gate,))
                assert await open_video(self, LocalFiles(Path(__file__).with_name('video-fixtures')), 'h264-aac.mp4')
                owner = self.video_player
                playing = lambda: bool(native_value(owner.native.native.player, 'isPlaying'))
                await until(playing)
                for _ in range(2):
                    post('UIApplicationWillResignActiveNotification')
                    await asyncio.sleep(1.2)
                    self.screen_privacy.refresh()
                    assert playing(), 'Temporary inactivity paused video'
                    assert not gate.locked
                    if protected:
                        assert self.screen_privacy.shield is not None
                    post('UIApplicationDidBecomeActiveNotification')
                    await asyncio.sleep(.3)
                    assert playing()
                    assert not gate.locked
                post('UIApplicationWillResignActiveNotification')
                post('UIApplicationDidEnterBackgroundNotification')
                await until(lambda: not playing())
                if protected:
                    assert gate.locked
                post('UIApplicationDidBecomeActiveNotification')
                await asyncio.sleep(.5)
                assert not playing(), 'Background return resumed playback'
                if protected:
                    assert gate.locked
                    self.screen_privacy.lock_password.value = 'synthetic-password'
                    await self.screen_privacy.unlock()
                    assert not gate.locked
                await owner.close()
                if release:
                    release()
                    release = None
                report['cases'].append(dict(protected=protected, temporary_inactivity_kept_playing=True,
                    background_paused=True, background_locked=protected))
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            if release:
                release()
        (Path(self.paths.cache) / 'control-center-result.json').write_text(json.dumps(report, indent=2))


def main():
    return ControlCenterProbe('Control Center QA', 'io.github.ispaure.logisticsnotebookqa')
