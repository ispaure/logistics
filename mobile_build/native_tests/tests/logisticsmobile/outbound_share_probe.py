"""Exercise file ownership and Android Sharesheet from a disposable Logistics build."""
import asyncio
from hashlib import sha256
from pathlib import Path

from commonUtils.testing.stages import TestStage
from mobile.favourites import catalog
from mobile.outbound_share import SEND, _root, prune
from services.documents.mobile_storage import document_copies

from .document_workspace_probe import DocumentWorkspaceProbe

TEST_STAGE = TestStage.REGRESSION
RESULT = 'outbound-share-result.json'
STAGE = 'outbound-share-stage'
NAME = 'Selected payload.logisticsfixture'
OPEN = 'Open owner.txt'
PAYLOAD = b'Logistics share fixture\x00\xff\xe2\x98\x83\r\n' * 133


class OutboundShareProbe(DocumentWorkspaceProbe):
    result_name = RESULT

    async def run_checks(self, app, report):
        cache = Path(app.paths.cache)
        assert await app.show_files(location=('Local files', ''))
        provider = app.file_provider
        (provider.root / OPEN).write_bytes(b'Open document bytes\n')
        (provider.root / NAME).write_bytes(PAYLOAD)
        assert await app.open_crypt(copies=document_copies(provider), key=OPEN)
        session = app.private_sessions.active.session
        assert await app.show_files(location=('Local files', ''))
        browser = app.file_browser

        async def native_action(label):
            entry = next(entry for entry in browser.tree.entries.values()
                         if entry.payload and entry.payload.get('path') == NAME)
            await browser.select(entry)
            menu = browser.show_item_menu(app.file_item_commands(row=entry.payload))
            index = next(i for i, (title, _) in enumerate(menu.actions) if title == label)
            native = menu.native.getListView()
            assert native.performItemClick(native.getChildAt(index), index, native.getItemIdAtPosition(index))
            await asyncio.sleep(.15)

        await native_action('Add to Favourites')
        await self.wait_until(lambda: bool(catalog(app).entries()))
        assert [row['title'] for row in catalog(app).entries()] == [NAME]
        assert session.id in app.workspace.sessions
        await native_action('Remove from Favourites')
        await self.wait_until(lambda: not catalog(app).entries())
        report['cases'].append('selected-file-favourite-and-remove-with-open-owner-retained')

        for step in ('cancel', 'deliver'):
            await native_action(SEND)
            await self.wait_until(lambda: tuple(_root(app).glob('share-*/payload/*')))
            (cache / STAGE).write_text(step)
            if step == 'cancel':
                await self.wait_until(lambda: not tuple(_root(app).glob('share-*')))
                report['cases'].append('cancel-cleans-staged-copy')
        await self.wait_until((cache / 'outbound-receiver-verified').is_file)
        assert (provider.root / NAME).read_bytes() == PAYLOAD
        assert (provider.root / OPEN).read_bytes() == b'Open document bytes\n'
        assert session.id in app.workspace.sessions
        report.update(sha256=sha256(PAYLOAD).hexdigest(), bytes=len(PAYLOAD))
        report['cases'].append('recipient-verified-exact-bytes-and-expiration')
        prune(_root(app))
        assert not tuple(_root(app).glob('share-*'))
        report['cases'].append('expired-staging-pruned')

    @staticmethod
    async def wait_until(predicate):
        for _ in range(350):
            if predicate():
                return
            await asyncio.sleep(.1)
        raise TimeoutError('Outgoing share checkpoint did not complete')


def main():
    return OutboundShareProbe('Outgoing Share QA', 'io.github.ispaure.logisticsstorageqa')
