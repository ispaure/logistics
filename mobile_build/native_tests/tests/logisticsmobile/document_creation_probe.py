"""Disposable native creation flow with the compiled LocalCrypt bridge."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
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

    async def new_form(self):
        picker = self.editor_picker()
        original = picker._accepts
        rejected = []
        def accepts(work):
            result = original(work)
            if not result:
                rejected.append(dict(same_work=picker._work is work,
                    epoch=(work.epoch, picker._epoch), active=picker.active_host,
                    cancelled=work.cancel.is_set(), same_client=self.cloud_client is work.client,
                    credentials=(work.credential_generation, getattr(self.cloud_client, 'generation', None)),
                    navigation=(work.navigation, self.navigation_generation),
                    location=(work.location, (picker.save_as_storage.value, picker.picker_folder.value))))
            return result
        picker._accepts = accepts
        try:
            await self.choose_document_type()
            for _ in range(100):
                if picker.editor_picker_location is not None and not picker.cloud_busy:
                    return picker
                await asyncio.sleep(.1)
            raise AssertionError(('Creation form did not finish loading',
                picker.editor_picker_location, picker.save_as_status.value, rejected))
        finally:
            picker._accepts = original

    async def create_in(self, filename, location, kind='Plain text (.txt)'):
        self.show_home()
        before = self.store.documents()
        form = await self.new_form()
        form.save_as_name.value = filename
        form.creation_type.value = kind
        picker = self.editor_picker()
        assert self.store.documents() == before
        assert not any(label.startswith('Remote') for label in picker.editor_storage_roots)
        assert picker.editor_picker_location == ('All files', '')
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
        if owner.crypt_reader.kind in ('.md', '.markdown'):
            owner.crypt_edit_mode.value = 'Source'
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

    async def create_notebook(self):
        from features.notebooks.notebook import Notebook
        self.show_home()
        form = await self.new_form()
        form.save_as_name.value = 'Native notebook'
        form.creation_type.value = 'Notebook (.rmdoc)'
        await asyncio.sleep(.3)
        picker = self.editor_picker()
        assert picker.editor_picker_location == ('All files', '')
        row = next(row for row in picker.editor_picker_rows.values() if row['name'] == 'Local')
        assert await picker.browser_editor_folder(row), picker.save_as_status.value
        assert picker.picker_parent.enabled
        await picker.parent_editor_folder()
        assert picker.editor_picker_location == ('All files', '')
        assert await picker.browser_editor_folder(row), picker.save_as_status.value
        picker.new_folder_name.value = 'Test'
        await picker.create_picker_folder()
        assert picker.picker_folder.value == 'Test', picker.save_as_status.value
        assert picker.effective_name.text == 'Save as: Native notebook.rmdoc'
        picker.save_as_name.value = 'Invalid.txt'
        await picker.confirm_editor_file()
        assert 'ending in .rmdoc' in picker.save_as_status.value
        backend = type(picker.save_as_status._impl).__module__
        if backend.startswith('toga_android.'):
            native = picker.save_as_status.label._impl.native
            assert str(native.getText()) == picker.save_as_status.value
            assert native.getHeight() > 0
        picker.save_as_name.value = 'Native notebook'
        path = picker.editor_provider('Local').root / 'Test/Native notebook.rmdoc'
        await picker.confirm_editor_file()
        assert path.is_file(), picker.save_as_status.value
        assert Notebook.read(path.read_bytes()).name == 'Native notebook'
        assert self.notebook_panel.session.provider == 'notebook'
        assert self.close_session(self.notebook_panel.session.id)
        return dict(location='Local / Test', format='rmdoc', validation_retry=True)

    async def check_creation(self):
        output = Path(self.paths.cache) / 'document-creation-evidence'
        output.mkdir(parents=True, exist_ok=True)
        report = dict(success=False, cases=[])
        try:
            report['cases'].append(await self.create_in('Ordinary.txt', 'Local'))
            report['cases'].append(await self.create_in('Note.md', 'Received Files', 'Markdown (.md)'))
            report['cases'].append(await self.create_notebook())
            self.show_cloud(present=False)
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
            fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
            self.cloud_client.request('import', package=fixture['package'], password='synthetic-session-password',
                                      package_name='Synthetic.zip', session_only=True)
            remote = next(iter(fixture['copies'].values()))['record']['remote']
            self.cloud_crypt_remotes = {remote}
            from features.rclone.localcrypt.mobile.resources import CryptFiles
            from services.documents.storage import DocumentResource
            provider = CryptFiles(self.private_root / 'LocalCryptFolders', self.cloud_client, remote)
            DocumentResource.publish(provider, 'Existing.txt', b'Encrypted fixture', max_bytes=1024)
            report['cases'].append(await self.create_in('Encrypted.txt', 'LocalCrypt: ' + remote))
            self.show_home()
            form = await self.new_form()
            form.save_as_name.value = 'My notebook'
            form.creation_type.value = 'Notebook (.rmdoc)'
            await form.browser_editor_location(('Local', ''))
            await asyncio.sleep(.5)
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))


def main():
    return CreationProbe('Document Creation QA', BUNDLE)
