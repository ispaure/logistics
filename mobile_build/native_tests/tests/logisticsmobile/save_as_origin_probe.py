"""Focused native Save As Cancel/Back origin check using synthetic local documents."""
import asyncio
import json
from pathlib import Path
import traceback
from mobile.app import LogisticsMobile
from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.resources import LocalTextCopies


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'save-as-origin-fixture'
        super().startup()

    def on_running(self):
        if not getattr(self, '_origin_probe_started', False):
            self._origin_probe_started = True
            self.loop.create_task(self.check())

    async def check(self):
        result = dict(success=False, backend=type(self._impl).__module__)
        try:
            self.show_cloud(present=False)
            restoring = getattr(self, 'cloud_restore_task', None)
            if restoring is not None:
                await restoring
            root = Path(self.storage_root) / 'Source'
            root.mkdir(exist_ok=True)
            (root / 'Earlier.txt').write_text('Earlier saved text')
            assert await self.open_crypt(copies=LocalTextCopies(LocalFiles(root)), key='Earlier.txt', edit=True)
            provider = self.provider_sessions().active
            self.new_document(name='New draft.txt', content='Origin draft remains intact')
            document, owner = self.current, self.editor_view
            for action in ('cancel', 'back'):
                await self.show_document_save_as()
                await asyncio.sleep(.3)
                picker = self.editor_picker()
                assert picker.origin.owner is owner
                if action == 'cancel':
                    picker.cancel_text_destination()
                else:
                    assert self.routes.back()
                await asyncio.sleep(.3)
                assert self.current is document and self.editor_view is owner
                assert self.current.text == 'Origin draft remains intact'
                assert self.provider_sessions().active is provider
                assert picker.origin is None
            await self.show_crypt_save_as(owner=provider)
            self.editor_picker().cancel_text_destination()
            await asyncio.sleep(.3)
            assert self.provider_sessions().active is provider
            result.update(success=True, managed_cancel=True, managed_back=True,
                          provider_cancel=True, draft_preserved=True)
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'save-as-origin-result.json').write_text(json.dumps(result))


def main():
    return Probe('Save As origin QA', 'io.github.ispaure.logisticsrefactorqa')
