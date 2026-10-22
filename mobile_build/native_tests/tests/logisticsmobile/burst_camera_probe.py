"""Simulator-only native Home/camera presentation and unavailable-camera check."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from mobile.app import LogisticsMobile


class BurstCameraProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('burst-camera-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        from rubicon.objc import ObjCClass, objc_method, objc_id
        from .fixtures import png_page
        from base64 import b64encode

        class LGBurstFixturePhoto(ObjCClass('NSObject')):
            @objc_method
            def fileDataRepresentation(self) -> objc_id:
                return ObjCClass('NSData').alloc().initWithBase64EncodedString(
                    b64encode(png_page()).decode(), options=0)

        class LGBurstInvalidFixturePhoto(ObjCClass('NSObject')):
            @objc_method
            def fileDataRepresentation(self) -> objc_id:
                return ObjCClass('NSData').alloc().initWithBase64EncodedString(
                    'bm90LWEtcGhvdG8=', options=0)
        from .fixtures import capture_window
        report = {'success': False, 'scope': 'simulator presentation; no physical photos'}
        try:
            await asyncio.sleep(1)
            self.show_settings()
            self.settings_navigation.choose('Camera')
            await asyncio.sleep(.5)
            await capture_window(self, Path(self.paths.cache) / 'burst-settings.png')
            self.preferences.save(burst_camera='front', burst_photos_per_second='3')
            from mobile.preferences import Preferences
            reopened = Preferences(self.preferences.path.parent)
            assert reopened.values['burst_camera'] == 'front'
            assert reopened.values['burst_photos_per_second'] == '3'
            self.show_home()
            await asyncio.sleep(.5)
            button = self.home_content.children[-1]
            assert button.text == 'Burst camera'
            await capture_window(self, Path(self.paths.cache) / 'burst-home.png')
            button._impl.native.sendActionsForControlEvents(64)
            await asyncio.sleep(2)
            root = self.main_window._impl.native.rootViewController
            controller = root.presentedViewController
            assert controller is not None
            assert controller.isKindOfClass(ObjCClass('LGBurstCameraController'))
            assert str(controller.cameraKey) == 'front'
            assert float(controller.framesPerSecond) == 3
            assert abs(float(controller.captureInterval()) - 1 / 3) < .000001
            report['saved_camera_applied'] = 'front'
            report['saved_rate_applied'] = 3
            assert len(controller.rateChoice.menu.children) == 30
            assert controller.cameraChoice.menu is not None
            controller.selectCameraKey('front', rate=5)
            await asyncio.sleep(.5)
            assert self.preferences.values['burst_photos_per_second'] == '5'
            assert float(controller.framesPerSecond) == 5
            assert abs(float(controller.captureInterval()) - .2) < .000001
            assert self._burst_preference_controls[1].value == '5'
            controller.selectCameraKey('rear_wide', rate=5)
            await asyncio.sleep(.5)
            assert self.preferences.values['burst_camera'] == 'rear_wide'
            assert self._burst_preference_controls[0].value == 'Rear main (1×) (unavailable)'
            report['viewer_settings_shared'] = True
            report['status'] = str(controller.status.text)
            assert 'No camera available' in report['status'], report
            assert not controller.shutter.isEnabled()
            controller.beginBurst()
            await asyncio.sleep(.2)
            assert not controller.holding
            await capture_window(self, Path(self.paths.cache) / 'burst-camera.png')
            # Exercise the actual native persistence/PhotoKit callback with a
            # synthetic image. This does not exercise the sensor or exposure.
            fixture = LGBurstFixturePhoto.alloc().init()
            controller.captureOutput(controller.output, didFinishProcessingPhoto=fixture, error=None)
            for _ in range(100):
                await asyncio.sleep(.1)
                if int(controller.saved) or int(controller.failures):
                    break
            report['synthetic_photos_saved'] = int(controller.saved)
            report['save_failures'] = int(controller.failures)
            assert report['synthetic_photos_saved'] == 1 and not report['save_failures'], report
            pending = Path(self.paths.data) / 'Local/Camera Pending'
            assert not list(pending.glob('*')), 'Successfully saved original was not removed'
            controller.holding = True
            invalid = LGBurstInvalidFixturePhoto.alloc().init()
            controller.captureOutput(controller.output, didFinishProcessingPhoto=invalid, error=None)
            for _ in range(100):
                await asyncio.sleep(.1)
                if int(controller.failures) and not controller.holding:
                    break
            report['failed_save_retains_original'] = len(list(pending.glob('*'))) == 1
            report['failed_save_stops_burst'] = not bool(controller.holding)
            assert report['failed_save_retains_original'] and report['failed_save_stops_burst'], report
            controller.finish()
            await asyncio.sleep(.6)
            assert root.presentedViewController is None
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'burst-camera-result.json').write_text(json.dumps(report, indent=2))


def main():
    return BurstCameraProbe('Burst Camera QA', 'io.github.ispaure.logisticsburstqa')
