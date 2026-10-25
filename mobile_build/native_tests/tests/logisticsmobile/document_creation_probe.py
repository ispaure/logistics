"""Disposable native creation flow with the compiled LocalCrypt bridge."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from mobile.app import LogisticsMobile

BUNDLE = 'io.github.ispaure.logisticscreationqa'


class CreationProbe(LogisticsMobile):
    def startup(self):
        import logging
        logging.getLogger().addHandler(logging.FileHandler(Path(self.paths.cache) / 'markdown-qa-python.log', mode='w'))
        self.storage_root = Path(self.paths.cache) / ('creation-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not hasattr(self, 'creation_check'):
            self.creation_check = self.loop.create_task(self.check_creation())

    async def create_in(self, filename, location):
        self.show_home()
        before = self.store.documents()
        self.choose_document_type()
        form = self.body.children[0].content
        form.name_input.value = filename
        await form.create_button.on_press()
        picker = self.editor_picker()
        assert self.store.documents() == before
        assert not any(label.startswith('Remote') for label in picker.editor_storage_roots)
        picker.save_as_storage.value = location
        # UIKit may finish its push after the async action returns. Match a
        # user's next action after presentation, rather than cancelling the
        # listing with a still-pending navigation generation change.
        await asyncio.sleep(.3)
        assert await picker.refresh_editor_browser(), picker.save_as_status.value
        await picker.confirm_editor_file()
        owner = self.private_sessions.active
        assert owner is not None, picker.save_as_status.value
        assert owner.crypt_reader.name == filename
        content = 'Native created document: ' + location
        owner.crypt_text.value = content
        await owner.save_crypt()
        assert not owner.private_dirty()
        provider = owner._crypt_reader_store.provider
        assert filename in [row['name'] for row in provider.list()]
        if provider.private:
            raw = provider._physical(filename).read_bytes()
            assert raw and content.encode() not in raw
        else:
            assert (provider.root / filename).read_text() == content
        assert self.store.documents() == before
        assert all(route not in ('new-document', 'text-destination')
                   for route, *_ in self.routes.screens['home'])
        assert self.private_sessions.close(owner.session.id, discard=True)
        return dict(location=location, encrypted=provider.private)

    async def check_creation(self):
        output = Path(self.paths.cache) / 'document-creation-evidence'
        output.mkdir(parents=True, exist_ok=True)
        report = dict(success=False, cases=[])
        try:
            report['cases'].append(await self.create_in('Ordinary.txt', 'Local'))
            self.show_cloud(present=False)
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
            fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
            self.cloud_client.request('import', package=fixture['package'], password='synthetic-session-password',
                                      package_name='Synthetic.zip', session_only=True)
            remote = next(iter(fixture['copies'].values()))['record']['remote']
            self.cloud_crypt_remotes = {remote}
            report['cases'].append(await self.create_in('Encrypted.txt', 'LocalCrypt: ' + remote))
            self.show_home()
            self.choose_document_type()
            form = self.body.children[0].content
            form.name_input.value = 'Choose my folder'
            await form.create_button.on_press()
            await asyncio.sleep(.5)
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))


def main():
    return CreationProbe('Document Creation QA', BUNDLE)
