"""Run Notes Library playlist controls with the production native speech engine."""

import asyncio
import json
from pathlib import Path
import traceback

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from mobile.obsidian import open_vault
from .links_images_voices_probe import LinksImagesVoicesProbe

TEST_STAGE = TestStage.REGRESSION


class PlaylistSpeechProbe(LinksImagesVoicesProbe):
    async def probe(self):
        self.report = dict(success=False, backend=type(self._impl).__module__)
        cache = Path(self.paths.cache)
        owner = None
        try:
            if self.startup_task is not None:
                await asyncio.shield(self.startup_task)
            root = self.private_root / 'Playlist fixture'
            root.mkdir()
            (root / 'One.md').write_text(' '.join(['First passage'] * 15))
            (root / 'Silent.md').write_text('![Hidden](missing.png)')
            (root / 'Two.md').write_text(' '.join(['Second passage'] * 120))
            owner = await open_vault(self, LocalFiles(root), '', 'documents')
            owner.select_panel_tab('Playlist')
            pane = owner.playlist_panel
            await self.until(lambda: pane.loading is not None and pane.loading.done(), 'Playlist tab did not load')
            record = await asyncio.to_thread(pane.catalog.create, 'Synthetic playlist')
            for path in ('One.md', 'Silent.md', 'Two.md'):
                record = await asyncio.to_thread(pane.catalog.add, record.id, path)
            pane.playlist_id = record.id
            await pane.reload()
            self.record_stage('play')
            await self.tap(pane.play_button)
            speech = pane.speech
            await self.until(lambda: speech.state == 'speaking', 'Native playlist speech did not start', timeout=45)
            panel = speech.panel
            assert speech.active_id == record.entries[0].id
            await self.until(lambda: speech.queue.position > 0, 'No native or estimated word progress', timeout=20)
            self.record_stage('skip')
            await self.tap(panel.play_button)
            assert speech.state == 'paused'
            await self.tap(panel.skip_forward)
            await self.until(lambda: speech.active_id == record.entries[2].id, 'Forward skip did not cross the silent note')
            assert speech.state == 'paused' and speech.queue.position > 0
            await self.tap(panel.skip_back)
            await self.until(lambda: speech.active_id == record.entries[0].id, 'Backward skip did not return to the first note')
            assert speech.state == 'paused'
            self.report.update(success=True, stage='complete', voice_available=bool(panel.voice),
                               native_media=panel.playback.media is not None)
        except Exception:
            self.report['error'] = traceback.format_exc()
        finally:
            if owner is not None:
                owner.dispose()
            (cache / 'playlist-speech-result.json').write_text(json.dumps(self.report, indent=2))


def main():
    return PlaylistSpeechProbe('Playlist Speech QA', 'io.github.ispaure.logisticsnotebookqa')
