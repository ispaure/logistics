"""Native Files/Links drawer concealment across real application backgrounding."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.waiting import wait_until
from mobile.app import LogisticsMobile
from mobile.obsidian import open_vault
from mobile.screen_privacy import native_value
from .fixtures import capture_window

BUNDLE = 'io.github.ispaure.logisticsnotebookqa'
PASSWORD = 'synthetic-session-password'


class DrawerPrivacyProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'drawer-privacy-workspace'
        super().startup()

    def on_running(self):
        if not getattr(self, '_drawer_privacy_task', None):
            self._drawer_privacy_task = self.loop.create_task(self.probe())

    def publish(self):
        target = Path(self.paths.cache) / 'drawer-privacy-result.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.report, indent=2))
        temporary.replace(target)

    def assert_detached(self, drawers, native, backdrop):
        assert drawers.overlay is None and drawers.side is None
        assert not drawers.retiring
        assert native_value(native, 'superview') is None, 'Private drawer remains in the UIKit hierarchy'
        if backdrop is not None:
            assert native_value(backdrop, 'superview') is None, 'Private drawer backdrop remains attached'
        for overlay in tuple(getattr(self, '_speech_overlays', ())):
            assert overlay.container is None and overlay.popup is None
            assert overlay.backdrop is None

    async def probe(self):
        self.report = dict(success=False, phase='starting', cases=[])
        owner = None
        try:
            assert type(self._impl).__module__.startswith('toga_iOS.'), 'This probe certifies UIKit only'
            await wait_until(lambda: not getattr(self, '_startup_in_progress', False), timeout=60)
            self.show_cloud(present=False)
            for name in ('cloud_startup_task', 'cloud_restore_task'):
                pending = getattr(self, name, None)
                if pending is not None:
                    await asyncio.shield(pending)
            fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
            self.cloud_client.request('import', package=fixture['package'], password=PASSWORD,
                                      package_name='Synthetic drawer privacy.zip', session_only=True)
            privacy = self.screen_privacy
            await wait_until(privacy.sensitive, timeout=10)
            gate = self.cloud_client.session_privacy
            assert not gate.locked
            root = Path(self.paths.cache) / 'Private Drawer Library'
            (root / '.obsidian').mkdir(parents=True)
            (root / 'Home.md').write_text('# Synthetic private drawer content\n\n[[Other]]\n')
            (root / 'Other.md').write_text('# Synthetic private linked note\n\n[[Home]]\n')
            owner = await open_vault(self, LocalFiles(root), '', 'files')
            await owner.open_note('Home.md')
            original = self.main_window.content
            drawers = owner.sidebar
            assert not drawers.expanded, 'Use a compact iPhone allocation for floating Files'
            for side in ('files', 'links'):
                drawers.show(side)
                overlay = drawers.overlay
                assert overlay is not None and overlay.container is not None
                native, backdrop = overlay.container.native, overlay.backdrop
                await wait_until(lambda: native_value(native, 'superview') is not None, timeout=5)
                await capture_window(self, Path(self.paths.cache) / f'drawer-privacy-{side}-open.png')
                self.report.update(phase='await_background', side=side)
                self.publish()
                # The host's existing background handshake launches Settings,
                # then returns this isolated QA app. Never call conceal directly.
                (Path(self.paths.cache) / 'file-transfer-background').touch()
                await wait_until(lambda: gate.locked and not privacy.inactive and not privacy.interrupted
                                 and self.main_window.content is privacy.lock_view,
                                 timeout=30, message='Real background/return did not produce the resume challenge')
                self.assert_detached(drawers, native, backdrop)
                drawers.show(side)
                self.assert_detached(drawers, native, backdrop)
                await capture_window(self, Path(self.paths.cache) / f'drawer-privacy-{side}-returned.png')
                privacy.lock_password.value = 'wrong-synthetic-password'
                await privacy.unlock()
                assert gate.locked and self.main_window.content is privacy.lock_view
                drawers.show(side)
                self.assert_detached(drawers, native, backdrop)
                await capture_window(self, Path(self.paths.cache) / f'drawer-privacy-{side}-wrong.png')
                privacy.lock_password.value = PASSWORD
                privacy.lock_button._impl.native.sendActionsForControlEvents(1 << 6)
                await wait_until(lambda: not gate.locked, timeout=15)
                assert self.main_window.content is original
                assert privacy.lock_password.value == ''
                drawers.show(side)
                reopened = drawers.overlay
                assert reopened is not None and reopened is not overlay
                assert native_value(reopened.container.native, 'superview') is not None
                await capture_window(self, Path(self.paths.cache) / f'drawer-privacy-{side}-reopened.png')
                drawers.show_detail()
                drawers.finish_dismissals()
                self.report['cases'].append(dict(side=side, real_os_background=True,
                    original_native_panel_detached=True, locked_opening_blocked=True,
                    wrong_password_rejected=True, native_button_unlock=True,
                    original_root_restored=True, drawer_reopened=True))
                self.publish()
            self.report.update(success=True, phase='complete')
        except Exception:
            self.report.update(phase='failed', error=traceback.format_exc())
            traceback.print_exc()
        finally:
            if owner is not None:
                owner.sidebar.dispose()
            self.publish()
            print('DRAWER_PRIVACY_RESULT=' + json.dumps(self.report), flush=True)


def main():
    return DrawerPrivacyProbe('Drawer privacy QA', BUNDLE)
