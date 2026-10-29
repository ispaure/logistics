"""Physical BOOX cold LocalCrypt unlock using real native button taps."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import traceback

from .android_predictive_back_probe import AndroidPredictiveBackProbe, BUNDLE
from .android_document_navigation_probe import AndroidDocumentNavigationProbe


class BooxLocalCryptProbe(AndroidPredictiveBackProbe):
    async def press_localcrypt_control(self, name, button):
        from android.graphics import Rect
        native = button._impl.native
        rect = Rect()
        assert native.isShown() and native.getGlobalVisibleRect(rect)
        assert rect.width() > 0 and rect.height() > 0
        self.state['tap'] = [rect.centerX(), rect.centerY()]
        await AndroidDocumentNavigationProbe.action(self, name, 'tap')
        if name == 'workspace':
            await self.wait_until(lambda: bool(self.routes.screens['files'])
                and self.routes.screens['files'][-1][0] == 'unlock-credential',
                'Workspace tap did not present its unlock prompt')
        elif name == 'wrong-password':
            await self.wait_until(lambda: 'Unlock failed' in self.credential_unlock_status.text,
                                  'Wrong password did not leave a retry prompt')
        else:
            await self.wait_until(lambda: getattr(self, 'file_provider', None) is not None
                and self.file_provider.private and not self.cloud_busy,
                'Unlock did not resume the encrypted folder')

    async def check(self):
        self.sequence = 0
        self.state = dict(success=False, checks={}, phase='initializing', sequence=0, action='wait')
        self.publish()
        try:
            from android.os import Build
            self.state.update(device_model=str(Build.MODEL), android_version=str(Build.VERSION.RELEASE))
            await self.check_localcrypt()
            await self.settle_keyboard()
            self.adaptive.render()
            header = self.file_browser.location_bar
            assert self.file_source_tabs.parent is None
            assert not self.file_source_tabs.children
            assert self.file_source_tabs._impl.native.getParent() is None
            frame = getattr(self.files_view, '_workspace_frame', None)
            content = frame.main if frame is not None else self.files_view
            assert header.parent is content
            assert content.children[0] is header
            assert sum(child is header for child in content.children) == 1
            assert header._impl.native.isShown()
            self.state['folder_title'] = header.folder_name.value
            self.state['browser_frame'] = 'workspace' if frame is not None else 'plain'
            assert self.file_storage.parent is None
            self.state['checks'].update(self.localcrypt_result)
            self.state['checks']['native_source_strip_detached'] = True
            self.state['checks']['single_browser_location_header'] = True
            self.state['navigation_presentation'] = self.native_host.adapter.mode
            self.state['window_dp'] = [self.main_window.size.width, self.main_window.size.height]
            self.state.update(success=True, phase='complete', action='complete')
        except Exception:
            self.state.update(error=traceback.format_exc(), phase='failed', action='complete')
        self.publish()


def main():
    return BooxLocalCryptProbe('LocalCrypt BOOX QA', BUNDLE)
