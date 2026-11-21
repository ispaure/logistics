"""Prepare generated files for the owned iOS share-sheet journey."""
import asyncio
from hashlib import sha256
import os
from time import time

from commonUtils.testing.stages import TestStage
from mobile.favourites import catalog
from mobile.outbound_share import SEND, SHARE_LIFETIME, _root, prune
from services.documents.mobile_storage import document_copies

from .document_workspace_probe import DocumentWorkspaceProbe
from .outbound_share_probe import NAME, OPEN, PAYLOAD

TEST_STAGE = TestStage.REGRESSION
BUNDLE = 'io.github.ispaure.logisticsstorageqa'
RESULT = 'outbound-share-result.json'


class OutboundIOSProbe(DocumentWorkspaceProbe):
    result_name = RESULT

    async def run_checks(self, app, report):
        assert await app.show_files(location=('Local files', ''))
        provider = app.file_provider
        open_file, selected_file = provider.root / OPEN, provider.root / NAME
        open_bytes = b'Open document bytes\n'
        open_file.write_bytes(open_bytes)
        selected_file.write_bytes(PAYLOAD)
        assert await app.open_crypt(copies=document_copies(provider), key=OPEN)
        owner = app.private_sessions.active.session
        assert await app.show_files(location=('Local files', ''))

        root = _root(app)
        stale = root / 'share-expired-fixture'
        stale.mkdir(parents=True)
        (stale / NAME).write_bytes(PAYLOAD)
        expired = time() - SHARE_LIFETIME - 1
        os.utime(stale, (expired, expired))
        prune(root)
        assert not stale.exists()
        report['cases'].append('expired-staging-pruned')

        browser = app.file_browser
        row = next(row for row in browser.native_list.data if row.title == NAME)
        actions = await browser.native_list.menu_provider(row)
        assert next(action for action in actions if str(action.title) == SEND).image is not None
        browser.dismiss_item_menu()
        report['cases'].append('native-share-glyph')

        await self.wait_until(lambda: [item['title'] for item in catalog(app).entries()] == [NAME])
        await self.wait_until(lambda: not catalog(app).entries())
        report['cases'].append('favourite-and-remove-selected-file')

        for i in range(2):
            await self.wait_until(lambda: app._outbound_share_sheet if hasattr(app, '_outbound_share_sheet') else None)
            staged, = root.glob('share-*/payload/*')
            assert staged.name == NAME and staged.read_bytes() == PAYLOAD
            sheet, future = app._outbound_share_sheet
            assert str(sheet.objc_class.name) == 'UIActivityViewController'
            accepted = await asyncio.shield(future)
            assert accepted == bool(i)
            await self.wait_until(lambda: not tuple(root.glob('share-*')))
            report['cases'].append('share-staging-cleaned' if i else 'cancelled-staging-cleaned')

        assert owner.id in app.workspace.sessions
        assert open_file.read_bytes() == open_bytes and selected_file.read_bytes() == PAYLOAD
        report.update(filename=NAME, bytes=len(PAYLOAD), sha256=sha256(PAYLOAD).hexdigest())
        report['cases'].append('open-owner-retained')

    @staticmethod
    async def wait_until(predicate):
        async with asyncio.timeout(240):
            while not predicate():
                await asyncio.sleep(0.1)


def main():
    return OutboundIOSProbe('Outgoing Share QA', BUNDLE)
