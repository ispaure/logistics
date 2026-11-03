"""Native move progress, shared idle policy and real background interruption."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import time
import traceback
from uuid import uuid4
from commonUtils.runtime.resources.local import LocalFiles
from mobile.app import LogisticsMobile
from mobile.file_operations import FileOperationRequest
from mobile.keep_awake import AwakeLease
from . import start_native_check
from .fixtures import capture_window


class SlowReading:
    def __init__(self, stream, cancelled):
        self.stream, self.cancelled = stream, cancelled
    def __getattr__(self, name):
        return getattr(self.stream, name)
    def read(self, size=-1):
        if self.stream.completed:
            deadline = time.monotonic() + 30
            while not self.cancelled():
                if time.monotonic() > deadline:
                    raise TimeoutError('Background event did not cancel the move')
                time.sleep(.05)
            from commonUtils.runtime.operations import check_cancelled
            check_cancelled(self.cancelled)
        return self.stream.read(size)


class StreamFiles(LocalFiles):
    slow = True
    def local_move_path(self, path):
        return None
    def create_file(self, path, stream, **kwargs):
        return super().create_file(path, SlowReading(stream, kwargs['cancelled']) if self.slow else stream, **kwargs)


class FileTransferProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('file-transfer-' + uuid4().hex)
        super().startup()
    def on_running(self):
        start_native_check(self, lambda app: app.check())
    async def wait(self, condition):
        for _ in range(300):
            if condition():
                return
            await asyncio.sleep(.1)
        raise TimeoutError('File transfer checkpoint timed out')
    async def check(self):
        report = dict(success=False, cases=[])
        task = None
        try:
            from rubicon.objc import ObjCClass
            application = ObjCClass('UIApplication').sharedApplication
            original = bool(application.isIdleTimerDisabled())
            first, second = AwakeLease(self), AwakeLease(self)
            assert application.isIdleTimerDisabled()
            first.close()
            assert application.isIdleTimerDisabled()
            second.close()
            assert bool(application.isIdleTimerDisabled()) == original
            report['cases'].append('shared-idle-policy-restored-after-last-owner')
            self.show_cloud(present=False)
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
            await self.show_files(location=('Local files', ''))
            source = self.file_provider
            video = source.root / 'Fixture.mkv'
            video.write_bytes(b'x' * (16 * 1024 * 1024))
            destination = self.private_root / 'Destination'
            destination.mkdir()
            provider = StreamFiles(destination)
            self.file_roots['Destination'] = provider
            picker = self.editor_picker()
            await picker.show_destination(video.name, FileOperationRequest('move', source, video.name))
            await picker.browser_editor_location(('Destination', ''))
            task = asyncio.create_task(picker.confirm_editor_file())
            await self.wait(lambda: 'Copying ·' in picker.save_as_status.value and picker.move_progress.value > 0)
            assert picker.moving() and application.isIdleTimerDisabled()
            assert not self.select_destination('settings')
            assert picker.move_progress.value > 0
            await asyncio.sleep(.2)
            native = picker.move_progress._impl.native
            window = self.main_window._impl.native
            frame = native.convertRect(native.bounds, toView=window)
            assert 0 <= float(frame.origin.y) < float(window.bounds.size.height) / 2
            assert float(frame.size.width) > 0 and float(frame.size.height) > 0
            await capture_window(self, Path(self.paths.cache) / 'file-transfer-progress.png')
            (Path(self.paths.cache) / 'file-transfer-background').touch()
            await self.wait(lambda: not picker.moving())
            await task
            await self.wait(lambda: not self.screen_privacy.inactive)
            assert video.is_file() and not (destination / video.name).exists()
            assert not list(destination.iterdir())
            assert 'leaving the app or locking' in ' '.join(picker.save_as_status.value.split()), picker.save_as_status.value
            assert bool(application.isIdleTimerDisabled()) == original
            report['cases'].append('native-progress-navigation-veto-background-cancel-cleanup')
            provider.slow = False
            await picker.confirm_editor_file()
            assert not video.exists() and (destination / video.name).stat().st_size == 16 * 1024 * 1024
            assert not self.cloud_busy and picker._work is None
            assert bool(application.isIdleTimerDisabled()) == original
            report['cases'].append('retry-verifies-and-restores-idle-policy')
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        finally:
            if task is not None and not task.done():
                self.editor_picker().cancel()
                await task
        (Path(self.paths.cache) / 'file-transfer-result.json').write_text(json.dumps(report, indent=2))


def main():
    return FileTransferProbe('File transfer QA', 'io.github.ispaure.logisticsnotebookqa')
