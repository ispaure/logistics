"""Measure folder I/O, landing probes and native Notes Library row publication."""
import asyncio
import cProfile
import json
from io import BytesIO
from pathlib import Path
import pstats
from time import perf_counter
from unittest.mock import patch

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from features.rclone.localcrypt.mobile.resources import CryptFiles
from mobile.obsidian import open_vault
from mobile import appearance
from .document_workspace_probe import DocumentWorkspaceProbe

TEST_STAGE = TestStage.EXTENDED


class NotesFoldersProbe(DocumentWorkspaceProbe):
    result_name = 'notes-folders-result.json'

    async def run_checks(self, app, report):
        fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
        app.cloud_client.request('import', package=fixture['package'],
            password='synthetic-session-password', package_name='Synthetic.zip', session_only=True)
        report['folders'] = []
        for private in (False, True):
            root = app.private_root / ('FolderCrypt' if private else 'FolderLocal')
            root.mkdir(exist_ok=True)
            provider = CryptFiles(root, app.cloud_client, 'Secret') if private else LocalFiles(root)
            provider.mkdir('Library')
            provider.mkdir('Library/Folder')
            for index in range(40):
                await asyncio.to_thread(provider.create_file, f'Library/Folder/Note {index:02}.md',
                                        BytesIO(b'# Folder timing fixture'))
            for index in range(4):
                path = f'Library/Folder/Child {index}'
                provider.mkdir(path)
                await asyncio.to_thread(provider.create_file, path + f'/Child {index}.md', BytesIO(b'# Landing'))
            owner = await open_vault(app, provider, 'Library', 'documents')
            owner.sidebar.show_sidebar()
            await self.settle(owner)
            for cold in (True, False):
                if not cold:
                    await owner.toggle_folder('Library/Folder')
                    await self.settle(owner)
                timings = dict(storage='localcrypt' if private else 'local', cold=cold,
                               list_seconds=0, landing_seconds=0, row_seconds=0, publications=[], surface_paints=0)
                def measured(name, function):
                    def run(*args, **kwargs):
                        start = perf_counter()
                        try:
                            return function(*args, **kwargs)
                        finally:
                            timings[name] += perf_counter() - start
                    return run
                updates = owner.tree_updates
                def tree_updates():
                    iterator = updates()
                    try:
                        while True:
                            start = perf_counter()
                            try:
                                next(iterator)
                            except StopIteration:
                                return
                            finally:
                                timings['row_seconds'] += perf_counter() - start
                            yield
                    finally:
                        iterator.close()
                add = owner.rows.add
                def publish(*children):
                    timings['publications'].append(len(children))
                    return add(*children)
                painter = appearance._surface_painter
                paint = painter.paint
                def paint_surface(impl, style):
                    if painter.pending.get() is None:
                        timings['surface_paints'] += 1
                    return paint(impl, style)
                profile = cProfile.Profile()
                with patch.object(owner.library, 'folders', measured('list_seconds', owner.library.folders)), \
                     patch.object(owner.library, 'folder_pages', measured('landing_seconds', owner.library.folder_pages)), \
                     patch.object(owner, 'tree_updates', tree_updates), patch.object(owner.rows, 'add', publish), \
                     patch.object(painter, 'paint', paint_surface), \
                     patch.object(provider, 'open', side_effect=AssertionError('Folder expansion read document content')):
                    start = perf_counter()
                    profile.enable()
                    await owner.toggle_folder('Library/Folder')
                    await self.settle(owner)
                    profile.disable()
                    timings['total_seconds'] = perf_counter() - start
                stats = pstats.Stats(profile)
                timings['profile'] = [dict(file=key[0], line=key[1], function=key[2], calls=value[1],
                                           own=value[2], cumulative=value[3])
                    for key, value in sorted(stats.stats.items(), key=lambda item: -item[1][3])[:25]]
                assert len(owner.rows.children) == 45, len(owner.rows.children)
                assert timings['publications'] == [45], timings['publications']
                report['folders'].append(timings)
                print('NOTES_FOLDER_TIMING=' + json.dumps(timings), flush=True)
            owner.dispose()
            report['cases'].append('folder_expansion_' + ('localcrypt' if private else 'local'))

    async def settle(self, owner):
        task = getattr(owner, 'tree_task', None)
        if task is not None:
            await task
        await asyncio.sleep(.05)


def main():
    return NotesFoldersProbe('Notes Folders QA', 'io.github.ispaure.logisticsnotebookqa')
