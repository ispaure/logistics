"""Prepare disposable files for the UIKit long-press drag acceptance test."""

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "marcandre.voyer@gmail.com"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
import json
from pathlib import Path

from commonUtils.testing.stages import TestStage
from . import start_native_check
from .notebook_probe import NotebookProbe


TEST_STAGE = TestStage.EXTENDED


class FileDragGestureProbe(NotebookProbe):
    def on_running(self):
        start_native_check(self, type(self).prepare_fixture)

    async def prepare_fixture(self):
        startup = getattr(self, 'startup_task', None)
        if startup is not None:
            await asyncio.shield(startup)
        assert await self.show_files(location=('Local files', ''))
        root = self.file_provider.root
        (root / 'Drop destination').mkdir(exist_ok=True)
        (root / 'List source').mkdir(exist_ok=True)
        (root / 'List source' / 'nested.txt').write_text('List drag')
        (root / 'Tile source.txt').write_text('Tile drag')
        self.file_browser._show_mode('List')
        assert await self.browse_files()
        cache = Path(self.paths.cache)
        (cache / 'file-drag-fixture.json').write_text(json.dumps({'root': str(root)}))
        for _ in range(800):
            if not (root / 'List source').exists() and self.file_status.value == 'Moved to Drop destination.':
                assert self.file_path == 'Drop destination', 'List hover did not open the folder'
                assert (root / 'Drop destination/List source/nested.txt').read_text() == 'List drag'
                (cache / 'file-drag-list-opened.txt').write_text(self.file_path)
                assert await self.browser_file_location(('Local files', ''))
                self.file_browser.show_tiles()
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError('List move did not complete')
        for _ in range(800):
            if not (root / 'Tile source.txt').exists() and self.file_status.value == 'Moved to Drop destination.':
                assert self.file_path == 'Drop destination', 'Tile hover did not open the folder'
                assert (root / 'Drop destination/Tile source.txt').read_text() == 'Tile drag'
                (cache / 'file-drag-tiles-opened.txt').write_text(self.file_path)
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError('Tile move did not complete')

        destination = root / 'Drop destination' / 'Group destination'
        destination.mkdir()
        self.file_browser._show_mode('List')
        assert await self.browse_files()
        for _ in range(450):
            if (destination / 'Tile source.txt').exists():
                assert (destination / 'Tile source.txt').read_text() == 'Tile drag'
                assert (destination / 'List source/nested.txt').read_text() == 'List drag'
                assert not (destination.parent / 'Tile source.txt').exists()
                assert not (destination.parent / 'List source').exists()
                (cache / 'file-drag-result.json').write_text(json.dumps({'list_spring_opened': True,
                    'tiles_spring_opened': True, 'destination_bytes_match': True, 'batch_move_verified': True}))
                return
            await asyncio.sleep(.1)
        raise AssertionError('Group move did not complete')


def main():
    return FileDragGestureProbe('File Drag QA', 'io.github.ispaure.logisticsnotebookqa')
