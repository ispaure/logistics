"""Root and nested LocalCrypt moves through the native workspace item menu."""
import asyncio
import json
from io import BytesIO
from contextlib import ExitStack
from pathlib import Path

from commonUtils.testing.stages import TestStage
from features.rclone.localcrypt.mobile.resources import CryptFiles
from .document_workspace_probe import DocumentWorkspaceProbe

TEST_STAGE = TestStage.REGRESSION


class WorkspaceMoveProbe(DocumentWorkspaceProbe):
    result_name = 'workspace-move-result.json'

    async def run_checks(self, app, report):
        app.show_cloud(present=False)
        if getattr(app, 'cloud_restore_task', None):
            await app.cloud_restore_task
        fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
        app.cloud_client.request('import', package=fixture['package'],
            password='synthetic-session-password', package_name='Synthetic.zip', session_only=True)
        provider = CryptFiles(app.private_root / 'MoveFixture', app.cloud_client, 'Secret')
        provider.mkdir('nested')
        provider.mkdir('destination')
        with ExitStack() as resources:
            resources.callback(provider.acquire())
            for source in ('root.md', 'nested/note.md'):
                data = ('# Move ' + source).encode()
                await asyncio.to_thread(provider.create_file, source, BytesIO(data))
                await app.show_files()
                label = 'LocalCrypt: Move fixture'
                app.file_roots[label] = provider.reopen()
                app.update_file_locations()
                assert await app.browser_file_location((label, source.rpartition('/')[0])), app.file_status.value
                browser = app.file_browser
                entry = next(entry for entry in browser.tree.entries.values()
                             if entry.payload and entry.payload.get('path') == source)
                await browser.select(entry)
                menu = browser.show_item_menu(app.file_item_commands())
                menu.invoke(dict(menu.actions)['Move…'])
                menu.dispose()  # Native selection also dismisses the originating sheet.
                await asyncio.wait_for(asyncio.gather(*tuple(browser.work.tasks)), 60)
                picker = app.editor_picker()
                assert picker.operation.destination_action.path == source
                picker.save_as_storage.value = label
                await picker._storage_refresh
                await picker.browser_editor_location((label, 'destination'))
                assert picker.picker_primary.enabled, picker.save_as_status.value
                await picker.confirm_editor_file()
                assert 'Move finished' in app.file_status.value, app.file_status.value
                from features.rclone.localcrypt.mobile.resources import encrypted_copies
                target = 'destination/' + source.rpartition('/')[2]
                reader = await asyncio.to_thread(encrypted_copies(provider).open, target)
                assert reader.data == data
                reader.source.close()
                assert not provider._physical(source).exists()
                assert data not in provider._physical(target).read_bytes()
                report['cases'].append('workspace_menu_move_' + source)


def main():
    return WorkspaceMoveProbe('Workspace Move QA', 'io.github.ispaure.logisticsnotebookqa')
