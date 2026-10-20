"""Disposable native profiling; never installed as the ordinary app launcher."""
import asyncio
import cProfile
from io import StringIO
import json
from pathlib import Path
import pstats
import time
import traceback
from uuid import uuid4

from logisticsmobile.app import LogisticsMobile


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('performance-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_profiling_started', False):
            self._profiling_started = True
            self.loop.create_task(self.measure())

    async def measure(self):
        from logisticsmobile.folder_hub_ui import FolderHubUI
        from logisticsmobile.hub_ui import HubUI
        from features.rclone.mobile.storage_location import collection_path
        output = Path(self.paths.cache) / 'performance-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False, samples=[], fixture='4 locked LocalCrypt folders and matching retained remotes; no loaded credentials')
        restorations = []
        spans = []
        active = False

        def instrument(owner, name, label=None):
            original = getattr(owner, name)
            def measured(*args, **kwargs):
                if not active:
                    return original(*args, **kwargs)
                started = time.perf_counter()
                try:
                    return original(*args, **kwargs)
                finally:
                    spans.append(dict(name=label or name, ms=(time.perf_counter() - started) * 1000))
            setattr(owner, name, measured)
            restorations.append((owner, name, original))

        try:
            await asyncio.sleep(1)
            self.show_cloud(present=False)
            task = getattr(self, 'cloud_restore_task', None)
            if task is not None:
                await task
            # Only the isolated fixture's account-index lookups are supplied.
            # Normal folder discovery, native controls and layout run unchanged.
            names = ['Account-Books', 'Account-Comics', 'Account-Documents', 'Account-Notes']
            self.retained_credential_associations = lambda: [dict(zip='Fixture.zip', remotes=names,
                crypt_remotes=names, session_only=True)]
            self.hub_crypt_roots = {name: (name, 'fixture-' + str(index)) for index, name in enumerate(names)}
            base = collection_path(self.private_root, True)
            for _, identity in self.hub_crypt_roots.values():
                path = base / identity
                path.mkdir(parents=True, exist_ok=True)
                (path / 'fixture').write_bytes(b'fixture, not a user document')
            for name in ('checkpoint', 'save_workspace', 'refresh_documents'):
                instrument(LogisticsMobile, name)
            for name in ('folder_choices', 'build_folder_picker', 'update_folder_list', 'folder_picker_or_error'):
                instrument(FolderHubUI, name)
            instrument(HubUI, 'refresh_hub')
            instrument(type(self.adaptive), 'prepare', 'adaptive.prepare')
            instrument(type(self.adaptive), 'render', 'adaptive.render')
            instrument(type(self.routes), 'render', 'routes.render')
            self.native_host.activate('home')

            async def sample(destination, label, profile=False):
                nonlocal active
                self.select_destination('home')
                self.native_host.activate('home')
                await asyncio.sleep(.4)
                spans.clear()
                profiler = cProfile.Profile() if profile else None
                draw_future = self.loop.create_future()
                from java import dynamic_proxy, jclass
                class Draw(dynamic_proxy(jclass('android.view.ViewTreeObserver$OnDrawListener'))):
                    def onDraw(listener):
                        if not draw_future.done():
                            draw_future.set_result(time.perf_counter())
                native = self.native_host.root._impl.native
                listener = Draw()
                native.getViewTreeObserver().addOnDrawListener(listener)
                if profiler:
                    profiler.enable()
                active = True
                started = time.perf_counter()
                try:
                    assert self.select_destination(destination)
                    self.native_host.activate(destination)
                finally:
                    blocked = (time.perf_counter() - started) * 1000
                    active = False
                    if profiler:
                        profiler.disable()
                native.invalidate()
                try:
                    drawn = await asyncio.wait_for(draw_future, 5)
                finally:
                    native.getViewTreeObserver().removeOnDrawListener(listener)
                yielded = (time.perf_counter() - started) * 1000
                sample = dict(name=label, destination=destination, callback_ms=blocked,
                              next_draw_ms=(drawn - started) * 1000, yielded_ms=yielded,
                              spans=list(spans), profiled=profile)
                report['samples'].append(sample)
                if profiler:
                    profiler.dump_stats(str(output / (label + '.prof')))
                    stream = StringIO()
                    stats = pstats.Stats(profiler, stream=stream).strip_dirs()
                    stats.sort_stats('cumulative').print_stats(70)
                    stats.sort_stats('tottime').print_stats(40)
                    (output / (label + '.txt')).write_text(stream.getvalue())
                (output / 'result.json').write_text(json.dumps(report, indent=2))
                print('PERFORMANCE_SAMPLE=' + json.dumps(sample), flush=True)
                await asyncio.sleep(.4)

            for source in ('Local', 'rclone'):
                self.folder_source = source
                for index in range(3):
                    await sample('files', source + '-' + str(index))
                await sample('files', source + '-profile', profile=True)
            for destination in ('documents', 'settings', 'chat'):
                for index in range(2):
                    await sample(destination, destination + '-' + str(index))

            # Diagnostic counterfactual: preserve the existing root for repeated
            # Workspaces visits. This is a probe-only experiment, not a fix.
            original = HubUI.refresh_hub
            def retained(controller, destination):
                if destination == 'files':
                    return
                return original(controller, destination)
            HubUI.refresh_hub = retained
            try:
                for index in range(3):
                    await sample('files', 'retained-root-' + str(index))
            finally:
                HubUI.refresh_hub = original
            page = self.folder_picker_view
            self.change_folder_source('Local')
            local_rows = self.folder_list.children[0]
            self.change_folder_source('rclone')
            cloud_rows = self.folder_list.children[0]
            self.change_folder_source('Local')
            assert self.folder_list.children[0] is local_rows
            self.change_folder_source('rclone')
            assert self.folder_list.children[0] is cloud_rows
            original_names = self.loaded_remote_names
            try:
                self.loaded_remote_names = lambda: list(names)
                self.select_destination('files')
                assert self.folder_picker_view is page
                assert all(self.folder_buttons[name].parent.children[0].control_icon == 'folder_unlocked'
                           for name in names)
                self.loaded_remote_names = lambda: []
                self.select_destination('files')
                assert all(self.folder_buttons[name].parent.children[0].control_icon == 'folder_locked'
                           for name in names)
                self.change_folder_source('Local')
                assert all(self.folder_buttons[name].parent.children[0].control_icon == 'folder_locked'
                           for name in names)
            finally:
                self.loaded_remote_names = original_names
            folder = collection_path(self.private_root) / 'Added folder'
            folder.mkdir(parents=True)
            self.select_destination('files')
            assert 'Added folder' in self.folder_buttons
            folder.rmdir()
            self.select_destination('files')
            assert 'Added folder' not in self.folder_buttons
            assert self.folder_picker_view is page
            from .performance_workloads import measure_workloads
            report['workloads'] = await measure_workloads(self)
            report['memory_scope'] = 'Python allocations; native RSS requires platform profiler'
            report['regressions'] = ['retained page', 'source row reuse', 'unlock icons',
                                     'lock invalidates hidden sources', 'folder addition', 'folder removal']
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        finally:
            for owner, name, original in reversed(restorations):
                setattr(owner, name, original)
            (output / 'result.json').write_text(json.dumps(report, indent=2))
            print('PERFORMANCE_RESULT=' + json.dumps(dict(success=report['success'], error=report.get('error'))), flush=True)


def main():
    return Probe('Performance QA', 'io.github.ispaure.logisticsperformanceqa')
