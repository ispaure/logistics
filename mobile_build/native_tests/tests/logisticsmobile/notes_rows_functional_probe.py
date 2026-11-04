"""Android recycled-tree acceptance without timing or host-load requirements."""
from pathlib import Path
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from .notes_rows_performance_probe import NotesRowsPerformanceProbe, atomic_json

TEST_STAGE = TestStage.EXTENDED


class NotesRowsFunctionalProbe(NotesRowsPerformanceProbe):
    result_name = 'notes-rows-functional-result.json'

    def native_row_count(self, owner):
        return int(owner.rows.native_list._impl.native.getCount())

    async def measure(self, owner, storage, variant, cold, report):
        assert variant == 'recycled'
        folder = 'Library/Folder'
        if folder in owner.expanded:
            await owner.toggle_folder(folder)
            await self.settle(owner)
        if cold:
            owner.folders.pop(folder, None)
        publications = []
        publish = owner.rows.add

        def add(*rows):
            publications.append(len(rows))
            return publish(*rows)

        with patch.object(owner.rows, 'add', side_effect=add), patch.object(
                owner.provider, 'open', side_effect=AssertionError('Expansion read note bodies')):
            await owner.toggle_folder(folder)
            await self.settle(owner)
        assert publications == [45], publications
        assert len(owner.rows.children) == 45
        assert self.native_row_count(owner) == 45
        report['cases'].append(f'recycled_folder_{storage}_{"cold" if cold else "repeated"}')

    async def run_checks(self, app, report):
        atomic_json(Path(self.paths.cache) / 'notes-performance-config.json', dict(order=['recycled']))
        await super().run_checks(app, report)
        report['timing_acceptance'] = False


def main():
    return NotesRowsFunctionalProbe('Notes Row Functional QA', 'io.github.ispaure.logisticsnotebookqa')
