"""Physical Android checks with synthetic local files and a simulated busy transfer."""
import asyncio
import json
from pathlib import Path
from threading import Event
import traceback
from uuid import uuid4

import toga

from mobile.app import LogisticsMobile
from mobile.routes import contains
from .fixtures import make_books

BUNDLE = 'io.github.ispaure.logisticstransferfeedbackqa'


class TransferFeedbackProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('synthetic-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_feedback_started', False):
            self._feedback_started = True
            self.loop.create_task(self.check())

    def stage(self, name):
        (Path(self.paths.cache) / 'transfer-feedback-stage.json').write_text(json.dumps({'stage': name}))

    async def check(self):
        result = {'success': False, 'scope': 'Synthetic files and simulated transfer; no live account or transfer.'}
        try:
            restore = self.start_cloud_restore()
            if restore is not None:
                await restore
            self.show_cloud(present=False)
            await self.show_files()
            folder = self.private_root / 'LocalFiles'
            folder.mkdir(exist_ok=True)
            _, comic = make_books(folder)
            await self.open_download(path=comic)
            reader = self.readers.active
            reader.set_reading_mode(False)
            self.transfer_busy = True
            self.transfer_notification = True
            self.transfer_epoch = 1
            self._transfer_cancel = Event()
            self.set_cloud_busy(True)
            reader.reader_actions_button._impl.native.performClick()
            await asyncio.sleep(.5)
            menu = reader.reader_actions
            assert menu.menu.popup is not None
            assert menu.native_context() is self._impl.native
            self.stage('comic-menu')
            await asyncio.sleep(5)
            index = next(i for i, (title, _) in enumerate(menu.actions) if title == 'Comic pages…')
            menu.menu.popup.getMenu().performIdentifierAction(index, 0)
            await asyncio.sleep(.5)
            assert contains(self.body, reader.reader_tools_view)
            assert self.transfer_busy and not self._transfer_cancel.is_set()
            result['android_comic_popup_and_command_during_transfer'] = True
            self.routes.back()

            for destination in ('home', 'files', 'documents'):
                self.routes.return_to(destination)
                origin = self.body
                self.show_transfers()
                self.publish_mirror_progress(1, dict(phase='Transferring', files=2, total_files=4,
                    done=12500000, total=25000000, active=1, listed=12, checks=8))
                self.show_transfers()
                assert self.native_host.state.destination == destination
                assert self.transfer_progress.value == 50
                back = next(child for child in self.transfer_view.content.children
                            if isinstance(child, toga.Button) and child.text == 'Back')
                if destination == 'files':
                    self.stage('transfer-details')
                    await asyncio.sleep(5)
                back._impl.native.performClick()
                await asyncio.sleep(.3)
                assert self.body is origin
                assert self.transfer_busy and not self._transfer_cancel.is_set()
            result['native_back_button_keeps_each_origin_and_transfer'] = True

            self.show_transfers()
            self.stage('system-back')
            for _ in range(100):
                if self.body is origin:
                    break
                await asyncio.sleep(.1)
            assert self.body is origin
            assert self.transfer_busy and not self._transfer_cancel.is_set()
            result['android_system_back_returns_to_origin'] = True

            self.stage('cloud-dialog')
            assert not await self.open_remote_document(dict(path='Synthetic.txt', directory=False, size=1))
            assert self.transfer_busy and not self._transfer_cancel.is_set()
            result['native_cloud_preview_block_explains_transfer'] = True
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        finally:
            self.stage('complete')
            (Path(self.paths.cache) / 'transfer-feedback-result.json').write_text(json.dumps(result, indent=2))
            print('TRANSFER_FEEDBACK_RESULT=' + json.dumps(result), flush=True)


def main():
    return TransferFeedbackProbe('Transfer feedback QA', BUNDLE)
