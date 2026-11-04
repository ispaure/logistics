"""UIKit recycled-tree acceptance without a draw observer or timing windows."""
from unittest.mock import patch

import toga
from rubicon.objc import ObjCClass
from commonUtils.testing.stages import TestStage
from . import enable_native_fault_log
from .notes_rows_functional_probe import NotesRowsFunctionalProbe
from .notes_rows_ios_checks import check_tree_interactions

TEST_STAGE = TestStage.EXTENDED


class NotesRowsIOSFunctionalProbe(NotesRowsFunctionalProbe):
    result_name = 'notes-rows-ios-functional-result.json'

    def startup(self):
        self._notes_fault_stream = enable_native_fault_log(self.paths.cache)
        super().startup()

    def device_details(self, app):
        assert type(app._impl).__module__ == 'toga_iOS.app'
        device = ObjCClass('UIDevice').currentDevice
        return dict(system=str(device.systemVersion), model=str(device.model))

    def native_row_count(self, owner):
        table = owner.rows.native_list._impl.native
        table.layoutIfNeeded()
        return int(table.numberOfRowsInSection(0))

    async def measure(self, owner, storage, variant, cold, report):
        created = 0
        constructor = toga.Button.__init__

        def button(widget, *args, **kwargs):
            nonlocal created
            created += 1
            constructor(widget, *args, **kwargs)

        print(f'UIKit functional rows: {storage} {"cold" if cold else "repeated"}', flush=True)
        with patch.object(toga.Button, '__init__', button):
            await super().measure(owner, storage, variant, cold, report)
        table = owner.rows.native_list._impl.native
        visible = len(list(table.visibleCells))
        assert 0 < visible < 45, visible
        assert created == 0, created
        report.setdefault('native_expansions', []).append(dict(storage=storage, cold=cold,
            published_rows=45, visible_cells=visible, toga_buttons_created=created))

    async def interactions(self, owner, report):
        await check_tree_interactions(owner, report)

    async def run_checks(self, app, report):
        report.update(draw_observer_installed=False, timing_acceptance=False)
        await super().run_checks(app, report)


def main():
    return NotesRowsIOSFunctionalProbe('Notes UIKit Functional QA', 'io.github.ispaure.logisticsnotebookqa')
