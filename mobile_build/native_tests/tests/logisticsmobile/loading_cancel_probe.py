"""Cancel blocked document reads and verify the native destinations recover."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
from threading import Event
import traceback

import toga

from mobile.app import LogisticsMobile

BUNDLE = 'io.github.ispaure.logisticsloadingcancelqa'


class LoadingCancelProbe(LogisticsMobile):
    def startup(self):
        # The fixture never accepts external documents or OS share events.
        import mobile.incoming_files
        mobile.incoming_files.native_queues = lambda app: []
        self.storage_root = Path(self.paths.cache) / 'synthetic-workspace'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.check())

    async def check(self):
        result = dict(success=False, samples=[])
        try:
            from commonUtils.runtime.resources.local import LocalFiles
            from features.text_editor.resources import LocalTextCopies
            from .fixtures import capture_window
            path = self.private_root / 'Cancellation.txt'
            path.write_text('Synthetic cancellation fixture')
            for destination in ('home', 'files', 'documents'):
                started, release = Event(), Event()
                class DelayedCopies(LocalTextCopies):
                    def open(self, *args, **kwargs):
                        started.set()
                        if not release.wait(15):
                            raise RuntimeError('Blocked reading fixture timed out')
                        return super().open(*args, **kwargs)
                self.show_view(toga.Box(), destination=destination, root=True)
                task = self.loop.create_task(self.open_crypt(
                    copies=DelayedCopies(LocalFiles(path.parent)), key=path.name))
                try:
                    assert await asyncio.to_thread(started.wait, 10)
                    self.adaptive.render()
                    await asyncio.sleep(.1)
                    primary = self.adaptive.primary if destination == 'documents' and self.adaptive.split is not None else None
                    delegate = primary.delegate if primary is not None else None
                    # UIKit need not send another primary didShow callback when
                    # returning to an already retained list. Exercise that path.
                    if primary is not None:
                        primary.delegate = None
                    for owner in self.provider_sessions().controllers.values():
                        if owner._crypt_cancel is not None:
                            owner.cancel_cloud()
                    release.set()
                    try:
                        assert not await task
                    finally:
                        if primary is not None:
                            primary.delegate = delegate
                    adapter = self.native_host.adapter
                    hidden = (adapter.tabs_hidden() if hasattr(adapter, 'navigation') else
                              adapter.impl.native_navigationview.getVisibility() == 8)
                    sample = dict(destination=destination, hidden=hidden,
                                  document_tabs_hidden=self._document_tabs_hidden,
                                  in_detail=self.adaptive.in_detail,
                                  routes=list(self.native_host.state.routes[destination]))
                    result['samples'].append(sample)
                    await capture_window(self, Path(self.paths.cache) / ('loading-cancel-' + destination + '.png'))
                    assert not hidden, sample
                    assert not self._document_tabs_hidden, sample
                    assert self._file_loading is None
                finally:
                    release.set()
                    await task
            result['success'] = True
        except BaseException:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'loading-cancel-result.json').write_text(json.dumps(result, indent=2))
        print('LOADING_CANCEL_RESULT=' + json.dumps(result), flush=True)


def main():
    return LoadingCancelProbe('Loading Cancel QA', BUNDLE)
