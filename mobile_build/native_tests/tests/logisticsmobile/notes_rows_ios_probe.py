"""UIKit first-draw comparison and recycled Notes interaction acceptance."""
import asyncio
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import toga
from rubicon.objc import ObjCClass
from commonUtils.testing.stages import TestStage
from commonUtils.ui.native.draw_ready import _install_draw_probe
from . import enable_native_fault_log
from .notes_rows_performance_probe import NotesRowsPerformanceProbe, atomic_json
from .notes_rows_ios_checks import check_tree_interactions

TEST_STAGE = TestStage.EXTENDED


class NotesRowsIOSProbe(NotesRowsPerformanceProbe):
    result_name = 'notes-rows-ios-result.json'

    def startup(self):
        self._notes_fault_stream = enable_native_fault_log(self.paths.cache)
        super().startup()

    def device_details(self, app):
        assert type(app._impl).__module__ == 'toga_iOS.app'
        device = ObjCClass('UIDevice').currentDevice
        return dict(system=str(device.systemVersion), model=str(device.model))

    async def measure(self, owner, storage, variant, cold, report):
        folder = 'Library/Folder'
        if folder in owner.expanded:
            await owner.toggle_folder(folder)
            await self.settle(owner)
        if cold:
            owner.folders.pop(folder, None)
        print(f'UIKit Notes rows: {storage} {variant} {"cold" if cold else "repeated"}', flush=True)
        drawn = owner.host.loop.create_future()
        cleanups = []
        sample = dict(storage=storage, variant=variant, cold=cold, buttons_created=0, publications=[])
        add, create = owner.rows.add, toga.Button.__init__

        def painted():
            now = perf_counter()
            def finish():
                if not drawn.done():
                    drawn.set_result(now)
            owner.host.loop.call_soon_threadsafe(finish)

        def publish(*rows):
            sample['publications'].append(len(rows))
            result = add(*rows)
            if len(rows) == 45:
                panel = owner.rows.widget if getattr(owner.rows, 'recycled', False) else owner.rows
                cleanup = _install_draw_probe(panel, painted)
                assert cleanup is not None, 'UIKit draw observer could not be installed'
                cleanups.append(cleanup)
            return result

        def button(widget, *args, **kwargs):
            sample['buttons_created'] += 1
            create(widget, *args, **kwargs)

        try:
            with patch.object(owner.rows, 'add', publish), patch.object(toga.Button, '__init__', button), \
                    patch.object(owner.provider, 'open', side_effect=AssertionError('Expansion read a note body')):
                start = perf_counter()
                await owner.toggle_folder(folder)
                end = await asyncio.wait_for(drawn, timeout=60)
                sample['first_draw_seconds'] = end - start
            await self.settle(owner)
            assert sample['publications'] == [45], sample
            assert len(owner.rows.children) == 45
            if variant == 'recycled':
                table = owner.rows.native_list._impl.native
                sample['visible_cells'] = len(list(table.visibleCells))
                sample['bound_cells'] = len(owner.rows.native_list._impl._tree_cells)
                assert 0 < sample['visible_cells'] < 45, sample
                assert sample['buttons_created'] == 0, sample
            else:
                assert sample['buttons_created'] >= 45, sample
            report['measurements'].append(sample)
        finally:
            for cleanup in cleanups:
                cleanup()

    async def interactions(self, owner, report):
        await check_tree_interactions(owner, report)

    async def run_checks(self, app, report):
        atomic_json(Path(self.paths.cache) / 'notes-performance-config.json',
                    dict(order=['legacy', 'recycled', 'recycled', 'legacy']))
        await super().run_checks(app, report)


def main():
    return NotesRowsIOSProbe('Notes UIKit Rows QA', 'io.github.ispaure.logisticsnotebookqa')
