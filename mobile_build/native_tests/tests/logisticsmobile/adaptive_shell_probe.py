"""Real shell frames across retained tabs, rotation and external audio changes."""
import asyncio
import json
from pathlib import Path
import traceback

from commonUtils.testing.stages import TestStage
from .ios_toolbar_probe import ToolbarProbe
from .toolbar_conventions_probe import native_geometry
from .rotation_checks import rotate, pose_snapshot

TEST_STAGE = TestStage.EXTENDED
BUNDLE = 'io.github.ispaure.logisticsconventionsqa'


class ShellProbe(ToolbarProbe):
    def on_running(self):
        if not getattr(self, '_shell_started', False):
            self._shell_started = True
            from rubicon.objc import ObjCClass
            self.static = '--static-shell' in [str(arg) for arg in ObjCClass('NSProcessInfo').processInfo.arguments]
            self.loop.create_task(self.check())

    async def record(self, name):
        sample = await super().record(name)
        sample['native'] = native_geometry(self, verify=False)
        sample['root_observation'] = getattr(self, '_ios_window_occlusions', None)
        view = self.routes.body().children[0]
        sample['home_header'] = bool(getattr(view, '_home_top_band', None))
        sample['reader_header'] = bool(getattr(view, '_reader_top_band_state', None))
        sample['destination_header'] = bool(getattr(view, '_destination_top_band', None))
        (self.output / 'progress.json').write_text(json.dumps(self.report, indent=2))
        return sample

    async def wait_phase(self, phase):
        from mobile.ios_reader_chrome import occlusion_geometry
        native = self.main_window._impl.native
        if phase == 'audio':
            self.idle_regions = occlusion_geometry(native)
        (self.output / 'ready').write_text(phase)
        for _ in range(600):
            command = self.output / 'continue'
            if command.exists() and command.read_text() == phase:
                command.unlink()
                # Playback-ready is not a guarantee that SpringBoard has
                # published its activity yet. Require real region movement
                # before recording an unchanged-size transition.
                for _ in range(150):
                    regions = occlusion_geometry(native)
                    if (regions != self.idle_regions if phase == 'audio' else regions == self.idle_regions):
                        await asyncio.sleep(2)
                        return
                    await asyncio.sleep(.2)
                raise AssertionError('External media did not produce the expected reserved-region transition: ' + phase)
            await asyncio.sleep(.2)
        raise TimeoutError('Host did not deliver ' + phase)

    async def sweep(self, phase):
        for name, show in (('home', self.show_home), ('documents', self.show_documents_hub),
                           ('workspaces', self.show_locations), ('chat', self.show_chat),
                           ('settings', self.show_settings)):
            show()
            await self.record(phase + '-' + name)
        self.show_documents_hub()
        for repeat in range(2):
            for step, pose in enumerate(('portrait', 'landscape-right', 'portrait')):
                await rotate(self, pose)
                await self.record(f'{phase}-documents-{repeat}-{step}-{pose}')
                self.show_home()
                await self.record(f'{phase}-home-{repeat}-{step}-{pose}')
                self.show_documents_hub()
        # Synthetic retained metadata exposes Unlock without reading credentials.
        # Keep the native buttons, handlers and system geometry real.
        from unittest.mock import patch
        for locked in (False, True):
            with patch.object(self, 'home_unlock_candidates', return_value=[('shell-qa', {'zip': 'QA.zip'})] if locked else []):
                self.show_documents_hub()
                for section in ('Libraries', 'Open', 'Recent', 'Saved'):
                    self.document_view_buttons[section]._impl.native.sendActionsForControlEvents(1 << 6)
                    assert self.documents_view == section
                    for step, pose in enumerate(('portrait', 'landscape-right', 'portrait')):
                        await rotate(self, pose)
                        await self.record(f'{phase}-{section}-{locked}-{step}-{pose}')
                self.show_home()
                await self.record(f'{phase}-home-unlock-{locked}')
        self.show_documents_hub()
        view = self.routes.body().children[0]
        if getattr(view, '_destination_top_band', None):
            view._document_search_button._impl.native.sendActionsForControlEvents(1 << 6)
            await asyncio.sleep(.5)
            assert self.documents_search_open
            view._document_search_close._impl.native.sendActionsForControlEvents(1 << 6)
            await asyncio.sleep(.5)
            assert not self.documents_search_open
            self.main_window._impl.native.endEditing(True)
            await self.record(phase + '-native-search-round-trip')
        self.show_settings()
        for title in self.settings_navigation.sections:
            self.settings_navigation.choose(title)
            await self.record(phase + '-settings-' + title.lower().replace(' ', '-'))
        from services.documents.mobile_notebooks import open_notebook
        self.set_feature_enabled('notebooks', True, refresh=False)
        for repeat in range(2):
            self.show_home()
            assert await open_notebook(self, key=getattr(self, '_shell_notebook_key', None),
                                       name='Shell fixture', destination='documents')
            self._shell_notebook_key = self.notebook_panel.key
            await self.record(f'{phase}-notebook-{repeat}')
            await rotate(self, 'landscape-right')
            await self.record(f'{phase}-notebook-{repeat}-landscape')
            await rotate(self, 'portrait')
        # Leave a live reader in place across the host's external media change.
        # Match the device's initial physical pose: launching the external
        # media app restores that pose after our scene-only rotation sweep.
        await rotate(self, self.boundary_pose)
        await self.record(phase + '-activity-boundary')

    async def check(self):
        self.output = Path(self.paths.cache) / 'shell-qa'
        self.output.mkdir(exist_ok=True)
        self.report = dict(success=False, screens=[], checks=[], system_split_view_verified=False)
        try:
            await asyncio.sleep(2)
            self.boundary_pose = {1: 'portrait', 3: 'landscape-left',
                                  4: 'landscape-right'}[pose_snapshot(self)['interface_orientation']]
            phases = ('idle',) if self.static else ('idle', 'audio', 'stopped')
            for phase in phases:
                if phase != 'idle':
                    await self.wait_phase(phase)
                    await self.record(phase + '-unchanged-reader')
                await self.sweep(phase)
            adapter = self.native_host.adapter
            root = getattr(adapter, '_logistics_shell_root', None)
            if root is not None:
                from mobile.ios_reader_chrome import install_shell_root, restore_shell_root
                window = self.main_window._impl.native
                original_title = self.main_window._impl.container.title
                self.main_window._impl.container.title = 'Shell lifecycle QA'
                restore_shell_root(adapter)
                assert window.rootViewController == adapter.outer_navigation
                assert adapter.outer_navigation.topViewController == adapter.parent
                assert str(adapter.parent.title) == 'Shell lifecycle QA'
                install_shell_root(adapter, root.objc_class)
                self.main_window._impl.container.title = original_title
                assert window.rootViewController == adapter._logistics_shell_root
                self._reader_chrome_hidden = True
                assert window.rootViewController.prefersStatusBarHidden
                self._reader_chrome_hidden = False
                await self.record('shell-containment-round-trip')
            states = {row['name']: row for row in self.report['screens']}
            for destination in ('home', 'documents', 'workspaces', 'chat', 'settings'):
                # The sweep can end in a different orientation; compare the
                # explicit portrait Documents round trips instead below.
                assert all(phase + '-' + destination in states for phase in phases)
            if not self.static:
                # No navigation or size change occurs between the idle reader
                # and either external activity transition. The front display
                # expands vertically, as does the open landscape display.
                transitions = [states[name] for name in ('idle-activity-boundary',
                    'audio-unchanged-reader', 'stopped-unchanged-reader')]
                assert len({(row['width'], row['height']) for row in transitions}) == 1
                regions = [row['native']['occlusions'] for row in transitions]
                self.report['activity_regions'] = regions
                assert regions[0] != regions[1] and regions[0] == regions[2], 'No observed activity expansion/contraction'
            collisions = [(row['name'], row['native']['collisions']) for row in self.report['screens']
                          if row['native']['collisions']]
            self.report['collisions'] = collisions
            assert not collisions, collisions
            self.report['checks'] = ['all-five-destinations', 'settings-categories',
                'two-documents-round-trips-per-phase', 'retained-home', 'repeated-notebook-entry',
                'documents-libraries-open-recent-saved-with-and-without-unlock',
                'native-control-and-reservation-frames']
            if not self.static:
                self.report['checks'].append('real-external-audio-expansion-contraction')
            self.report['success'] = True
        except BaseException:
            self.report['error'] = traceback.format_exc()
        finally:
            (self.output / 'result.json').write_text(json.dumps(self.report, indent=2))


def main():
    return ShellProbe('Adaptive shell QA', BUNDLE)
