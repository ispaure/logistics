"""Native open-file deletion, Recent filtering and retained-copy acceptance."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from mobile.app import LogisticsMobile
from commonUtils.runtime.resources.local import LocalFiles
from services.documents.mobile_storage import document_copies

BUNDLE = 'io.github.ispaure.logisticsstorageqa'


class RecentDeletionProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('recent-deletion-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not hasattr(self, '_recent_check'):
            self._recent_check = self.loop.create_task(self.verify_recent())

    async def settled(self, owner):
        for _ in range(300):
            if not owner.operation_busy:
                await asyncio.sleep(.2)
                return
            await asyncio.sleep(.1)
        raise TimeoutError('Reader did not settle')

    def listed(self, source):
        identity = ('file-reference', self.recent_documents.reference_id(source))
        from mobile.hub_ui import session_identities
        return any(identity in session_identities(session, self.recent_documents)
                   for session, _ in self.recent_items())

    async def verify_recent(self):
        report = dict(success=False, cases=[], backend=type(self._impl).__module__)
        try:
            for _ in range(200):
                if not self.cloud_busy:
                    break
                await asyncio.sleep(.1)
            root = self.storage_root / 'deletion-fixtures'
            root.mkdir(parents=True, exist_ok=True)
            provider = LocalFiles(root)
            for suffix in ('.txt', '.md'):
                for dirty in (False, True):
                    path = root / ('Delete-open-' + str(dirty) + suffix)
                    path.write_text('# Original content\n')
                    assert await self.open_crypt(copies=document_copies(provider), key=path.name, edit=True)
                    owner = self.private_sessions.active
                    await self.settled(owner)
                    workflow = getattr(owner, '_provider_markdown', None)
                    if workflow is not None:
                        await workflow.choose_mode('Source')
                    if dirty:
                        owner.crypt_text.value = '# Retained unsaved edits\n'
                    expected = owner.crypt_text.value
                    source = owner.session.history_source
                    assert self.listed(source), 'Open file absent before deletion'
                    path.unlink()
                    self.show_home()
                    await asyncio.sleep(.3)
                    assert self.listed(source), 'Live buffer must remain accessible'
                    await self.recent_opener(owner.session)()
                    assert owner.crypt_text.value == expected
                    if dirty:
                        await owner.save_crypt()
                        assert 'Save failed' in owner.crypt_title.text, owner.crypt_title.text
                        assert owner.crypt_text.value == expected and owner.private_dirty()
                    assert not path.exists(), 'Deletion was silently undone'
                    assert self.close_session(owner.session.id, choice='discard')
                    self.show_home()
                    self.show_documents_hub()
                    await asyncio.sleep(.3)
                    assert not self.listed(source), 'Closed deleted file remains in Recent'
                    assert not path.exists(), 'Closing recreated deleted file'
                    report['cases'].append(dict(format=suffix, dirty=dirty,
                        live_buffer_retained=True, save_rejected=dirty, absent_after_close=True))

            # Delete after rendering a closed Recent row, then activate that row.
            path = root / 'Delete-after-row.txt'
            path.write_text('Original')
            assert await self.open_crypt(copies=document_copies(provider), key=path.name, edit=True)
            owner = self.private_sessions.active
            await self.settled(owner)
            source = owner.session.history_source
            assert self.close_session(owner.session.id, choice='discard')
            self.show_home()
            recent = next(session for session, _ in self.recent_items()
                          if getattr(session, 'source', None) == source)
            row = self.recent_row(recent, self.session_summary(recent))
            path.unlink()
            original_dialog = self.main_window.dialog
            dialogs = []
            async def acknowledge(dialog):
                task = self.loop.create_task(original_dialog(dialog))
                await asyncio.sleep(.4)
                native = dialog._impl.native
                assert native.isShowing()
                dialogs.append(str(native.getWindow().getDecorView()))
                native.getButton(-1).performClick()
                return await asyncio.wait_for(task, 10)
            self.main_window.dialog = acknowledge
            try:
                await row.children[0].children[0].on_press()
            finally:
                self.main_window.dialog = original_dialog
            assert dialogs and not self.listed(source) and not path.exists()
            report['cases'].append('stale-row-shows-native-dialog-and-refreshes-home')

            from tests.logisticsmobile.fixtures import make_books
            book, _ = make_books(root)
            assert await self.open_download(path=book)
            owner = self.readers.active
            for _ in range(300):
                if not owner.book_busy:
                    break
                await asyncio.sleep(.1)
            session = owner.session
            book.unlink()
            assert self.close_session(session.id, choice='discard')
            self.show_home()
            recent, summary = next(item for item in self.recent_items() if item[0].identity == session.identity)
            row = self.recent_row(recent, summary)
            assert 'Saved copy on device' in row.children[-1].text
            await row.children[0].children[0].on_press()
            assert self.readers.active.session.identity == session.identity
            report['cases'].append('retained-book-copy-labelled-and-reopens-after-original-deletion')
            self.show_home()
            self.show_documents_hub()
            await asyncio.sleep(.5)
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'recent-deletion-result.json').write_text(json.dumps(report, indent=2))


def main():
    return RecentDeletionProbe('Recent deletion QA', BUNDLE)
