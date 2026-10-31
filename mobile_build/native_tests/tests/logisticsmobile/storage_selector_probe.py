"""Keep the download location selector open through native keyboard relayout."""
from commonUtils.testing.waiting import wait_until
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import traceback
from uuid import uuid4
from mobile.app import LogisticsMobile
from . import start_native_check
from .rotation_checks import rotate, pose_snapshot


class StorageSelectorProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('selector-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def probe(self):
        report = dict(success=False, backend=type(self._impl).__module__, samples=[])
        try:
            await asyncio.sleep(.5)
            self.show_cloud(present=False)
            picker = self.editor_picker()
            await picker.show_destination('download.txt', SimpleNamespace(
                kind='download', title='Download locally', primary='Download here'))
            await asyncio.sleep(.5)
            for orientation in ('portrait', 'landscape-left', 'portrait'):
                await rotate(self, orientation, settle=.4)
                control = picker.save_as_storage
                native = control._impl.native
                apple = type(self._impl).__module__.startswith('toga_iOS.')
                if apple:
                    assert native.becomeFirstResponder(), 'Selector could not open'
                else:
                    native.performClick()
                await asyncio.sleep(1)
                assert control.parent is picker.panel, 'Location selector was detached'
                if apple:
                    assert native.isFirstResponder, 'Location selector dismissed itself'
                for label in ('Shared files', 'Local files'):
                    index = next(i for i, item in enumerate(control.items)
                                 if control._title_for_item(item) == label)
                    if apple:
                        assert native.becomeFirstResponder()
                        await asyncio.sleep(.3)
                        assert native.isFirstResponder, 'Reopening location selector failed'
                        impl = control._impl
                        impl.native_picker.selectRow(index, inComponent=0, animated=False)
                        impl.native_picker.pickerView_didSelectRow_inComponent_(impl.native_picker, index, 0)
                    else:
                        native.setSelection(index)
                    await wait_until(lambda: picker.editor_picker_location == (label, '') and not picker.cloud_busy,
                        timeout=10, message='Location listing did not settle: ' + label)
                report['samples'].append(dict(orientation=orientation, pose=pose_snapshot(self),
                    location=picker.editor_picker_location, attached=True))
                if apple:
                    native.resignFirstResponder()
                else:
                    self._impl.native.onBackPressed()
                await asyncio.sleep(.3)
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'storage-selector-result.json').write_text(json.dumps(report, indent=2))


def main():
    return StorageSelectorProbe('Storage selector QA', 'io.github.ispaure.logisticsnotebookqa')
