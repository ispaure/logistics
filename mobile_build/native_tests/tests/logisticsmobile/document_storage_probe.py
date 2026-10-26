"""Real-widget notebook resource, binary publication and privacy acceptance."""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
from threading import Event
import traceback
from uuid import uuid4

from mobile.app import LogisticsMobile

BUNDLE = 'io.github.ispaure.logisticsstorageqa'


class DocumentStorageProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('document-storage-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not hasattr(self, '_storage_probe'):
            self._storage_probe = self.loop.create_task(self.verify_storage())

    async def wait(self, condition, timeout=30):
        deadline = self.loop.time() + timeout
        while self.loop.time() < deadline:
            if condition():
                return
            await asyncio.sleep(.1)
        raise TimeoutError('Native document state did not arrive.')

    async def command(self, panel, action):
        await panel.web.evaluate_javascript('send(' + json.dumps(action) + ')')
        # The canvas busy flag covers its pending bridge command, before the
        # Python handler has had a chance to reserve its own busy state.
        for _ in range(300):
            await asyncio.sleep(.1)
            if panel.web is not None and not panel.busy:
                if await panel.web.evaluate_javascript('!busy'):
                    return
        raise TimeoutError('Notebook canvas command was not acknowledged.')

    async def create_notebook(self, location, name):
        self.show_home()
        self.choose_document_type()
        form = self.body.children[0].content
        form.name_input.value, form.type_selector.value = name, 'Notebook (.rmdoc)'
        await form.create_button.on_press()
        picker = self.editor_picker()
        await asyncio.sleep(.4)
        picker.save_as_storage.value = location
        await asyncio.sleep(.3)
        assert await picker.refresh_editor_browser(), picker.save_as_status.value
        await picker.confirm_editor_file()
        panel = self.notebook_panel
        assert panel.editor is not None, picker.save_as_status.value
        for _ in range(200):
            try:
                if await panel.web.evaluate_javascript('typeof send === "function"'):
                    break
            except ValueError:
                pass
            await asyncio.sleep(.1)
        else:
            raise TimeoutError('Native notebook WebView did not load.')
        return panel

    @contextmanager
    def answer_native_dialog(self, answer, reports):
        original = self.main_window.dialog
        async def answer_dialog(dialog):
            task = self.loop.create_task(original(dialog))
            await asyncio.sleep(.3)
            native = dialog._impl.native
            if type(self._impl).__module__.startswith('toga_android.'):
                assert native.isShowing()
                native.getButton(-1 if answer else -2).performClick()
            else:
                assert native.presentingViewController is not None
                native.dismissViewControllerAnimated(False, completion=None)
                dialog._impl.response(answer)
            reports.append(dict(title=getattr(dialog, 'title', 'confirmation'), accepted=answer))
            return await asyncio.wait_for(task, 10)
        self.main_window.dialog = answer_dialog
        try:
            yield
        finally:
            self.main_window.dialog = original

    async def verify_formats(self, remote, fixture, report):
        import base64
        from commonUtils.runtime.resources.local import LocalFiles
        from features.rclone.localcrypt.mobile.resources import CryptFiles, ManagedCopies
        from services.documents.locations import collection_path
        from services.documents.mobile_storage import document_copies
        from services.documents.storage import DocumentResource
        local_root = collection_path(self.private_root)
        local_root.mkdir(parents=True, exist_ok=True)
        local = LocalFiles(local_root)
        crypt = CryptFiles(self.private_root / 'LocalCryptFolders', self.cloud_client, remote)
        for provider in (local, crypt):
            for suffix in ('.txt', '.md', '.ini', '.py'):
                name = 'Storage text' + suffix
                DocumentResource.publish(provider, name, b'# Original\n', max_bytes=1024 * 1024)
                assert await self.open_crypt(copies=document_copies(provider), key=name, edit=True)
                owner = self.private_sessions.active
                await self.wait(lambda: not owner.operation_busy)
                if suffix == '.md':
                    workflow = owner._provider_markdown
                    for _ in range(150):
                        try:
                            await workflow.flush()
                            break
                        except ValueError as error:
                            if 'not ready' not in str(error):
                                raise
                            await asyncio.sleep(.1)
                    else:
                        raise TimeoutError('Native Markdown editor did not become ready.')
                    await workflow.choose_mode('Source')
                    assert workflow.edit_mode.value == 'Source'
                owner.crypt_text.value = '# Native edited ' + suffix + '\n'
                await owner.save_crypt()
                assert not owner.private_dirty(), owner.crypt_title.text
                with DocumentResource(provider, name, max_bytes=1024 * 1024, independent=False) as resource:
                    assert resource.read() == owner.crypt_text.value.encode()
                await self.wait(lambda: not owner.operation_busy)
                assert self.close_session(owner.session.id, choice='discard')
                await asyncio.sleep(.2)
                report['cases'].append(('localcrypt' if provider.private else 'local') + '-text-save-' + suffix)
        from features.text_editor.notes import NotesLibrary
        from services.documents.mobile_storage import document_source
        from mobile.obsidian import open_vault
        for provider in (local, crypt):
            provider.mkdir('BoundaryNotes')
            provider.mkdir('BoundaryNotes/.obsidian')
            library = NotesLibrary(provider, 'BoundaryNotes')
            key = await asyncio.to_thread(library.create, 'Shared note')
            copies, mapped = document_source(provider, key)
            reader = await asyncio.to_thread(copies.open, mapped)
            await asyncio.to_thread(copies.save, reader, '# Shared storage note\n')
            assert await asyncio.to_thread(library.read, key) == b'# Shared storage note\n'
            browser = await open_vault(self, provider, 'BoundaryNotes', 'files')
            assert browser is not None and await browser.open_note(key)
            if provider.private:
                assert browser.web.private_configured
            browser.dispose()
            report['cases'].append(('localcrypt' if provider.private else 'local') + '-notes-shared-create-save-private-preview')
        for name in ('plain.cbz', 'book.epub', 'encrypted.cbz', 'protected.epub'):
            item = fixture['copies'][name]
            crypt._physical(name).write_bytes(base64.b64decode(item['ciphertext']))
            password = 'synthetic-archive-password' if name in {'encrypted.cbz', 'protected.epub'} else ''
            self.crypt_password.value = password
            assert await self.open_crypt(copies=ManagedCopies(crypt.reopen()), key=name)
            owner = self.private_sessions.active
            await self.wait(lambda: not owner.operation_busy)
            before = owner.crypt_reader.page(0)
            owner.edit_crypt_metadata()
            field = 'title' if name.endswith('.epub') else 'Title'
            owner.crypt_metadata_fields[field].value = 'Storage metadata acceptance'
            await self.wait(lambda: not owner.operation_busy)
            await owner.save_crypt_metadata()
            assert not owner.private_dirty(), owner.crypt_metadata_status.text
            reader = owner.crypt_reader
            value = reader.book.values('title')[0] if reader.book else reader.comic.info.get_field('Title')
            assert value == 'Storage metadata acceptance'
            assert reader.page(0) == before
            await self.wait(lambda: not owner.operation_busy)
            assert self.close_session(owner.session.id, choice='discard')
            await asyncio.sleep(.2)
            report['cases'].append('localcrypt-metadata-' + name)
            if password:
                continue
            # Ordinary archive imports retain their established saved-copy policy.
            ordinary = local.root / ('Ordinary-' + name)
            with DocumentResource(crypt, name, max_bytes=32*1024*1024, independent=False) as resource:
                ordinary.write_bytes(resource.read())
            assert await self.open_download(path=ordinary)
            owner = self.readers.active
            await self.wait(lambda: not owner.book_busy)
            owner.show_book_metadata()
            owner.book_metadata_fields[field].value = 'Ordinary metadata acceptance'
            await owner.save_book_metadata()
            assert owner.book_metadata_status.text == 'Metadata saved to the imported copy.', owner.book_metadata_status.text
            await self.wait(lambda: not owner.book_busy)
            assert self.close_session(owner.session.id)
            await asyncio.sleep(.2)
            report['cases'].append('local-metadata-' + name)
        from .reader_flow_probe import pdf_bytes
        from features.pdf.mobile.copies import PDFCopies
        data = pdf_bytes()
        for provider in (local, crypt):
            DocumentResource.publish(provider, 'Storage.pdf', data, max_bytes=32*1024*1024)
            copies = ManagedCopies(crypt.reopen()) if provider.private else PDFCopies(provider)
            assert await self.open_crypt(copies=copies, key='Storage.pdf')
            owner = self.private_sessions.active
            await self.wait(lambda: not owner.operation_busy)
            assert owner.crypt_reader.read_only and owner.crypt_reader.pdf.count == 5
            assert self.close_session(owner.session.id, choice='discard')
            await asyncio.sleep(.2)
            report['cases'].append(('localcrypt' if provider.private else 'local') + '-pdf-read-only')

    async def verify_notebook_deletion(self, location, report):
        """Real canvas/provider deletion with controlled confirmation responses."""
        from features.notebooks.notebook import Notebook, MAX_ARCHIVE
        from services.documents.storage import DocumentResource
        panel = await self.create_notebook(location, 'Storage deletion acceptance')
        await self.command(panel, dict(op='stroke', points=[[20,30,.5],[40,50,.5]], tool=12, width=2))
        document, session = panel.document, panel.session
        resource = document.resource
        physical = resource.provider._physical(resource.path)
        original_dialog = self.main_window.dialog
        answer = 'cancel'
        async def decision(dialog):
            assert dialog.choices[0][1] == 'delete'
            report['dialogs'].append(dict(title=dialog.title, response=answer, controlled=True))
            return answer
        self.main_window.dialog = decision
        label = 'localcrypt' if not resource.policy.persistent else 'local'
        try:
            assert await panel.delete_document() is False
            assert physical.exists() and document.dirty and not panel.closed and not panel.busy
            report['cases'].append(label + '-notebook-delete-cancel')
            DocumentResource.publish(resource.provider, resource.path, Notebook.new('External').to_bytes(),
                max_bytes=MAX_ARCHIVE, expected_revision=resource.revision)
            answer = 'delete'
            try:
                await panel.delete_document()
            except ValueError:
                pass
            else:
                raise AssertionError('Delete accepted a changed source')
            assert physical.exists() and not document.source_deleted and document.dirty
            report['cases'].append(label + '-notebook-delete-stale-revision')
            resource.read()
            replacement = physical.read_bytes()
            forget = self.recent_documents.forget
            def unavailable(*args):
                raise OSError('Controlled history cleanup failure')
            self.recent_documents.forget = unavailable
            try:
                try:
                    await panel.delete_document()
                except OSError as error:
                    assert 'Controlled history' in str(error)
                else:
                    raise AssertionError('History cleanup failure was not reported')
            finally:
                self.recent_documents.forget = forget
            assert document.source_deleted and not physical.exists() and not panel.closed
            state = panel.state()
            assert state['read_only'] and state['can_delete'] and 'Deleted' in state['save_status']
            try:
                document.save()
            except ValueError as error:
                assert 'deleted' in str(error)
            else:
                raise AssertionError('Deleted document could still save')
            marker = None
            if document.recovery is not None:
                recovery = document.recovery.root / document.key
                assert document.recovery_deleted and not recovery.exists()
                recovery.mkdir()
                marker = recovery / 'replacement-owner'
                marker.write_bytes(b'new recovery owner')
            report['cases'].append(label + '-notebook-delete-partial-failure-readonly')
            physical.write_bytes(replacement)
            assert await panel.delete_document()
            assert panel.closed and session.id not in self.workspace.sessions
            assert physical.read_bytes() == replacement
            if marker is not None:
                assert marker.read_bytes() == b'new recovery owner'
            report['cases'].append(label + '-notebook-delete-retry-keeps-replacements')
            report['cases'].append(label + '-notebook-delete-source-recovery-session')
        finally:
            self.main_window.dialog = original_dialog

    async def verify_storage(self):
        report = dict(success=False, backend=type(self._impl).__module__, cases=[], dialogs=[])
        try:
            from features.notebooks.notebook import Notebook
            from commonUtils.runtime.resources.local import LocalFiles
            from mobile.document_mutations import prepare_document_mutation
            from mobile.file_operations import FileOperationRequest, retiring_work
            await asyncio.sleep(.5)
            self.show_cloud(present=False)
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
            fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
            self.cloud_client.request('import', package=fixture['package'], password='synthetic-session-password',
                package_name='DocumentStorageFixture.zip', session_only=True)
            remote = next(iter(fixture['copies'].values()))['record']['remote']
            self.cloud_crypt_remotes = {remote}
            await asyncio.sleep(.3)
            await self.verify_formats(remote, fixture, report)
            for location in ('Local', 'LocalCrypt: ' + remote):
                await self.verify_notebook_deletion(location, report)
            for location in ('Local', 'LocalCrypt: ' + remote):
                panel = await self.create_notebook(location, 'Storage acceptance')
                if location.startswith('LocalCrypt'):
                    assert panel.web.private_configured
                    from features.notebooks.canvas import editor_html
                    html = editor_html(panel.state(), panel.bridge.url).replace('<head>', '<head><script>window.storageAcceptanceLarge=true;</script>') + '<!--private-large-html-sentinel' + 'x' * (3*1024*1024) + '-->'
                    panel.web.set_content('https://logistics.invalid/notebooks/', html)
                    for _ in range(150):
                        if await panel.web.evaluate_javascript('window.storageAcceptanceLarge === true && typeof send === \"function\"'):
                            break
                        await asyncio.sleep(.1)
                    else:
                        raise TimeoutError('Large private HTML did not load in memory.')
                    if type(self._impl).__module__.startswith('toga_android.'):
                        assert not panel.web._impl._large_content_dir.exists(), 'Private HTML reached the toolkit disk cache'
                    else:
                        assert not bool(panel.web._impl.native.configuration.websiteDataStore.isPersistent())
                    report['cases'].append('private-notebook-nonpersistent-large-html')
                await self.command(panel, dict(op='stroke', points=[[30,40,.4],[50,60,.8]], tool=12, width=2))
                await self.command(panel, dict(op='add-page'))
                assert len(panel.editor.notebook.pages) == 2
                assert panel.document.dirty
                await self.command(panel, dict(op='save'))
                assert not panel.document.dirty
                resource = panel.document.resource
                data = await asyncio.to_thread(resource.read)
                parsed = Notebook.read(data)
                assert len(parsed.pages) == 2 and len(parsed.page(0).strokes) == 1, (len(parsed.pages), len(parsed.page(0).strokes))
                if location == 'Local':
                    assert (resource.provider.root / resource.path).read_bytes() == data
                    assert self.close_session(panel.session.id)
                    report['cases'].append('ordinary-notebook-create-canvas-save')
                    continue
                assert panel.session.transient and panel.document.recovery is None
                assert b'Storage acceptance' not in resource.provider._physical(resource.path).read_bytes()
                # Preserve a binary member above the text limit using real Go I/O.
                panel.editor.notebook.members['padding.bin'] = os.urandom(1100000)
                panel.document.checkpoint(panel.editor.notebook)
                await self.command(panel, dict(op='save'))
                assert not panel.document.dirty
                assert len(await asyncio.to_thread(resource.read)) > 1024 * 1024
                report['cases'].append('localcrypt-notebook-binary-save-above-text-limit')
                await self.command(panel, dict(op='stroke', points=[[80,90,.5],[100,110,.7]], tool=12, width=3))
                editor = panel.editor
                panel.retire_canvas()
                from features.notebooks.mobile.documents import open_notebook
                assert await open_notebook(self, key=panel.key)
                assert panel.editor is editor and panel.document.dirty and editor.undo
                for _ in range(150):
                    if await panel.web.evaluate_javascript('typeof send === "function"'):
                        break
                    await asyncio.sleep(.1)
                else:
                    raise TimeoutError('Resumed private canvas did not load.')
                await self.command(panel, dict(op='undo'))
                assert len(panel.editor.notebook.page(1).strokes) == 0
                await self.command(panel, dict(op='redo'))
                assert len(panel.editor.notebook.page(1).strokes) == 1
                assert panel._repository is None
                report['cases'].append('private-notebook-canvas-resume-retains-draft-and-undo')
                assert not self.clear_private_reader(), 'Requested lock discarded an unsaved private notebook'
                request = FileOperationRequest('rename', resource.provider, resource.path, 'Renamed.rmdoc')
                plan = await prepare_document_mutation(self, request)
                try:
                    await retiring_work(plan.execute, Event(), completed=plan.apply)
                finally:
                    plan.release()
                assert panel.document.resource.path == 'Renamed.rmdoc'
                await self.command(panel, dict(op='save'))
                assert len(Notebook.read(await asyncio.to_thread(panel.document.resource.read)).page(1).strokes) == 1
                report['cases'].append('notebook-dirty-lock-veto-and-live-rename')
                picker = self.editor_picker()
                await picker.show_notebook_destination(panel)
                await asyncio.sleep(.4)
                picker.save_as_name.value = 'Private copy.rmdoc'
                await picker.confirm_editor_file()
                assert panel.document.resource.path == 'Private copy.rmdoc', picker.save_as_status.value
                assert panel.session.transient
                report['cases'].append('private-to-private-notebook-save-as')
                with self.answer_native_dialog(False, report['dialogs']):
                    await panel.perform(dict(op='export'))
                assert panel.web is not None and not panel.closed
                report['cases'].append('native-decrypted-export-cancel')
                await picker.show_notebook_destination(panel)
                await asyncio.sleep(.4)
                picker.save_as_storage.value = 'Local files'
                await asyncio.sleep(.3)
                assert await picker.refresh_editor_browser()
                picker.save_as_name.value = 'Decrypted copy.rmdoc'
                with self.answer_native_dialog(True, report['dialogs']):
                    await picker.confirm_editor_file()
                assert not panel.session.transient, picker.save_as_status.value
                assert isinstance(panel.document.resource.provider, LocalFiles)
                report['cases'].append('native-confirmed-notebook-decrypted-save-as')
                assert self.close_session(panel.session.id)
                # Reopen the retained encrypted copy, then revoke its actual grant.
                from services.documents.storage import DocumentResource
                from features.notebooks.notebook import MAX_ARCHIVE
                from features.notebooks.mobile.documents import open_notebook
                provider = resource.provider.reopen()
                reopened = DocumentResource(provider, 'Private copy.rmdoc', max_bytes=MAX_ARCHIVE)
                assert await open_notebook(self, resource=reopened)
                key = self.notebook_panel.session.id
                self.cloud_client.clear()
                await asyncio.sleep(.3)
                self.screen_privacy.retire_stale()
                assert key not in self._notebook_views
                try:
                    reopened.read()
                except ValueError:
                    pass
                else:
                    raise AssertionError('Revoked notebook resource could still be read')
                report['cases'].append('private-notebook-reopen-and-real-credential-revocation')
            from commonUtils.runtime.resources.local import LocalFiles
            from services.documents.storage import DocumentResource
            folder = self.storage_root / 'removable-notebook-source'
            folder.mkdir()
            (folder / 'Recover.rmdoc').write_bytes(Notebook.new('Recoverable').to_bytes())
            resource = DocumentResource(LocalFiles(folder), 'Recover.rmdoc', max_bytes=MAX_ARCHIVE)
            assert await open_notebook(self, resource=resource)
            panel = self.notebook_panel
            for _ in range(150):
                if await panel.web.evaluate_javascript('typeof send === "function"'):
                    break
                await asyncio.sleep(.1)
            await self.command(panel, dict(op='stroke', points=[[20,30,.5],[40,50,.5]], tool=12, width=2))
            recovery_key = panel.key
            assert self.close_session(panel.session.id)
            folder.rename(self.storage_root / 'disconnected-notebook-source')
            assert await open_notebook(self, key=recovery_key)
            panel = self.notebook_panel
            assert panel.document.resource is None and panel.document.dirty
            assert len(panel.editor.notebook.page(0).strokes) == 1
            assert self.close_session(panel.session.id, choice='discard')
            report['cases'].append('ordinary-notebook-recovery-after-source-folder-disappears')
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'document-storage-result.json').write_text(json.dumps(report, indent=2))
        print('DOCUMENT_STORAGE_RESULT=' + json.dumps(report), flush=True)


def main():
    return DocumentStorageProbe('Document Storage QA', BUNDLE)
