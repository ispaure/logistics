"""UIKit first-draw comparison and recycled Notes interaction acceptance."""
import asyncio
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import toga
from rubicon.objc import ObjCClass, objc_property
from commonUtils.testing.stages import TestStage
from commonUtils.ui.native.draw_ready import _install_draw_probe
from . import enable_native_fault_log
from .notes_rows_performance_probe import NotesRowsPerformanceProbe, atomic_json
from .notes_tree_helpers import activate_entry, native_row_control

TEST_STAGE = TestStage.EXTENDED


class NotesDragSession(ObjCClass('NSObject')):
    localContext = objc_property(object)


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
        rows = owner.rows
        path = 'Library/Folder/Child 0'
        await activate_entry(owner, path)
        assert owner.path == path + '/Child 0.md'
        owner.sidebar.show_sidebar()
        await activate_entry(owner, path, expand=True)
        assert any(row.path == path + '/Child 0.md' for row in rows.children)
        await activate_entry(owner, path, expand=True)
        assert not any(row.path == path + '/Child 0.md' for row in rows.children)
        title = await native_row_control(owner, path)
        assert title.attributedText is not None
        choices = []

        async def cancel(dialog):
            choices.extend(value for _, value, _ in dialog.choices)
            return 'cancel'

        before = owner.path
        action = await native_row_control(owner, 'Library/Folder/Note 00.md', 'actions')
        with patch.object(owner.view.window, 'dialog', new=cancel):
            action.sendActionsForControlEvents(1 << 6)
            await asyncio.sleep(0)
            await asyncio.gather(*tuple(rows.tasks))
        assert {'rename', 'move', 'copy', 'delete'}.issubset(choices), choices
        assert owner.path == before
        icon = await native_row_control(owner, 'Library/Folder/Note 00.md', 'icon')
        # Resolve the native delegate installed on the visible image. This tests
        # its opaque authorization payload, not a physical drag/drop gesture.
        from toga_iOS.libs import NSIndexPath
        row = next(row for row in rows.children if row.path.endswith('/Note 00.md'))
        table = rows.native_list._impl.native
        cell = table.cellForRowAtIndexPath(NSIndexPath.indexPathForRow(row.index, inSection=0))
        interaction, delegate = cell.tree_drag
        session = NotesDragSession.alloc().init()
        items = delegate.dragInteraction_itemsForBeginningSession_(interaction, session)
        assert len(list(items)) == 1 and str(session.localContext) == owner.file_drag.token
        assert owner.file_drag.source == row.path
        delegate.dragInteraction_session_didEndWithOperation_(interaction, session, 0)
        assert owner.file_drag.source is None
        assert icon.userInteractionEnabled
        table.scrollToRowAtIndexPath(NSIndexPath.indexPathForRow(44, inSection=0),
                                    atScrollPosition=2, animated=False)
        last = await native_row_control(owner, 'Library/Folder/Note 39.md')
        assert str(last.text) == 'Note 39.md' and last.attributedText is None
        owner.dispose()
        assert str(last.text) == '' and last.attributedText is None
        assert not rows.children and rows.closed
        report['cases'].append('uikit_tree_interactions_and_retirement_' + report['interaction_storage'])

    async def run_checks(self, app, report):
        atomic_json(Path(self.paths.cache) / 'notes-performance-config.json',
                    dict(order=['legacy', 'recycled', 'recycled', 'legacy']))
        await super().run_checks(app, report)


def main():
    return NotesRowsIOSProbe('Notes UIKit Rows QA', 'io.github.ispaure.logisticsnotebookqa')
