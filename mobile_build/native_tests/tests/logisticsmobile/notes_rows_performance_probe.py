"""Paired Android first-draw timings gated by an external load observer."""
import asyncio
from contextlib import ExitStack, nullcontext
from io import BytesIO
import json
from pathlib import Path
from time import monotonic, perf_counter
from unittest.mock import patch
from uuid import uuid4

import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from features.rclone.localcrypt.mobile.resources import CryptFiles
from features.notes_library.mobile.notes_library import VaultBrowser
from mobile.obsidian import open_vault
from .document_workspace_probe import DocumentWorkspaceProbe
from .notes_tree_helpers import activate_entry, native_row_control

TEST_STAGE = TestStage.EXTENDED


def atomic_json(path, value):
    pending = path.with_suffix(path.suffix + '.tmp')
    pending.write_text(json.dumps(value, indent=2))
    pending.replace(path)


class NotesRowsPerformanceProbe(DocumentWorkspaceProbe):
    result_name = 'notes-rows-performance-result.json'

    async def wait_json(self, path, *, seconds=600):
        deadline = monotonic() + seconds
        while monotonic() < deadline:
            if path.exists():
                return json.loads(path.read_text())
            await asyncio.sleep(.1)
        raise AssertionError('Host load observer did not acknowledge ' + path.name)

    async def gate(self, label):
        nonce = uuid4().hex
        atomic_json(Path(self.paths.cache) / 'notes-performance-progress.json',
                    dict(nonce=nonce, label=label, phase='waiting'))
        grant = await self.wait_json(Path(self.paths.cache) / ('notes-performance-go-' + nonce + '.json'))
        assert grant['nonce'] == nonce and grant['eligible'] is True, grant
        return nonce

    async def measure(self, owner, storage, variant, cold, report):
        from io.github.ispaure.logisticsqa import ViewDrawProbe
        from android.os import Process
        label = dict(storage=storage, variant=variant, cold=cold)
        for attempt in range(3):
            if 'Library/Folder' in owner.expanded:
                await owner.toggle_folder('Library/Folder')
                await self.settle(owner)
            if cold:
                owner.folders.pop('Library/Folder', None)
            nonce = await self.gate(label)
            clock = ViewDrawProbe(owner.rows_scroll._impl.native)
            sample = dict(label, nonce=nonce, attempt=attempt, publications=[],
                          list_seconds=0, landing_seconds=0, row_seconds=0, buttons_created=0)
            def measured(key, function):
                def invoke(*args, **kwargs):
                    start = perf_counter()
                    try:
                        return function(*args, **kwargs)
                    finally:
                        sample[key] += perf_counter() - start
                return invoke
            original_updates, original_add = owner.tree_updates, owner.rows.add
            def updates():
                iterator = original_updates()
                try:
                    while True:
                        start = perf_counter()
                        try:
                            next(iterator)
                        except StopIteration:
                            return
                        finally:
                            sample['row_seconds'] += perf_counter() - start
                        yield
                finally:
                    iterator.close()
            def publish(*rows):
                sample['publications'].append(len(rows))
                result = original_add(*rows)
                if len(rows) == 45:
                    clock.arm()
                return result
            original_button = toga.Button.__init__
            def button(widget, *args, **kwargs):
                sample['buttons_created'] += 1
                original_button(widget, *args, **kwargs)
            try:
                with patch.object(owner.library, 'folders', measured('list_seconds', owner.library.folders)), \
                     patch.object(owner.library, 'folder_pages', measured('landing_seconds', owner.library.folder_pages)), \
                     patch.object(owner, 'tree_updates', updates), patch.object(owner.rows, 'add', publish), \
                     patch.object(toga.Button, '__init__', button), \
                     patch.object(owner.provider, 'open', side_effect=AssertionError('Expansion read a document body')):
                    cpu = int(Process.getElapsedCpuTime())
                    clock.start()
                    await owner.toggle_folder('Library/Folder')
                    deadline = monotonic() + 120
                    while not clock.hasDrawn() and monotonic() < deadline:
                        await asyncio.sleep(.005)
                    assert clock.hasDrawn(), 'No frame after complete row publication'
                    sample['first_draw_seconds'] = float(clock.elapsedSeconds())
                    sample['process_cpu_ms'] = int(Process.getElapsedCpuTime()) - cpu
                await self.settle(owner)
                assert len(owner.rows.children) == 45
                assert sample['publications'] == [45], sample
                if variant == 'recycled':
                    view = owner.rows.native_list._impl.native
                    sample['visible_cells'] = int(view.getChildCount())
                    sample['created_cells'] = int(view.getCreatedRowCount())
                    sample['viewport_height'] = int(view.getHeight())
                    sample['density'] = float(view.getResources().getDisplayMetrics().density)
                    assert view.getCount() == 45
                    assert 0 < sample['visible_cells'] < 45, sample
                    assert sample['visible_cells'] <= sample['viewport_height'] / (48 * sample['density']) + 2
                    assert sample['buttons_created'] == 0, sample
                else:
                    assert sample['buttons_created'] >= 45, sample
            finally:
                clock.dispose()
            atomic_json(Path(self.paths.cache) / 'notes-performance-window.json', sample)
            decision = await self.wait_json(Path(self.paths.cache) / ('notes-performance-decision-' + nonce + '.json'))
            assert decision['nonce'] == nonce
            sample['load_accepted'] = decision['accepted']
            sample['load_reason'] = decision['reason']
            report['attempts'].append(sample)
            if decision['accepted']:
                report['measurements'].append(sample)
                return
        raise AssertionError('Three measurement windows rejected by load controls: ' + str(label))

    async def settle(self, owner):
        task = getattr(owner, 'tree_task', None)
        if task is not None:
            await task
        await asyncio.sleep(.05)

    async def interactions(self, owner, report):
        from android.graphics import Paint
        rows = owner.rows
        await activate_entry(owner, 'Library/Folder/Child 0')
        assert owner.path == 'Library/Folder/Child 0/Child 0.md'
        owner.sidebar.show_sidebar()
        await activate_entry(owner, 'Library/Folder/Child 0', expand=True)
        assert any(row.path.endswith('/Child 0.md') for row in rows.children)
        await activate_entry(owner, 'Library/Folder/Child 0', expand=True)
        assert not any(row.path.endswith('/Child 0.md') for row in rows.children)
        title = await native_row_control(owner, 'Library/Folder/Child 0')
        assert title.getPaintFlags() & Paint.UNDERLINE_TEXT_FLAG
        choices = []
        async def cancel(dialog):
            choices.extend(value for _, value, _ in dialog.choices)
            return 'cancel'
        before = owner.path
        action = await native_row_control(owner, 'Library/Folder/Note 00.md', 'actions')
        with patch.object(owner.view.window, 'dialog', new=cancel):
            assert action.performClick()
            await asyncio.gather(*tuple(rows.tasks))
        assert {'rename', 'move', 'copy', 'delete'}.issubset(choices), choices
        assert owner.path == before
        owner.sidebar.show_sidebar()
        icon = await native_row_control(owner, 'Library/Folder/Note 00.md', 'icon')
        # performLongClick has no physical pointer stream: Android may deliver
        # ACTION_DRAG_ENDED before it returns. Check the authorized source at
        # initiation rather than requiring a cancelled gesture to remain live.
        with patch.object(owner.view.window, 'dialog', new=cancel):
            with patch.object(owner.file_drag, 'start', wraps=owner.file_drag.start) as started:
                assert icon.performLongClick()
                started.assert_called_once_with('Library/Folder/Note 00.md')
            icon.cancelDragAndDrop()
            owner.file_drag.end()
            # The pointerless synthetic gesture can also queue ListView's
            # fallback context event. Retire it before testing viewport scroll.
            await asyncio.sleep(.1)
            await asyncio.gather(*tuple(rows.tasks))
        native = rows.native_list._impl.native
        created = int(native.getCreatedRowCount())
        native.setSelection(44)
        await asyncio.sleep(.15)
        last = await native_row_control(owner, 'Library/Folder/Note 39.md')
        assert str(last.getText()) == 'Note 39.md'
        assert not last.getPaintFlags() & Paint.UNDERLINE_TEXT_FLAG
        assert int(native.getCreatedRowCount()) - created <= 2 * native.getChildCount() + 2
        retained = last
        owner.dispose()
        assert str(retained.getText()) == '', 'Private title survived source retirement'
        assert not rows.children and rows.closed
        report['cases'].append('native_tree_interactions_and_retirement_' + report['interaction_storage'])

    async def run_checks(self, app, report):
        from android.os import Build
        assert type(app._impl).__module__ == 'toga_android.app'
        report['device'] = dict(api=int(Build.VERSION.SDK_INT), model=str(Build.MODEL))
        config = json.loads((Path(self.paths.cache) / 'notes-performance-config.json').read_text())
        fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
        app.cloud_client.request('import', package=fixture['package'], password='synthetic-session-password',
                                 package_name='Synthetic.zip', session_only=True)
        report.update(backend=type(app._impl).__module__, attempts=[], measurements=[], order=config['order'])
        for private in (False, True):
            storage = 'localcrypt' if private else 'local'
            root = app.private_root / ('RowsCrypt' if private else 'RowsLocal')
            root.mkdir(exist_ok=True)
            provider = CryptFiles(root, app.cloud_client, 'Secret') if private else LocalFiles(root)
            with ExitStack() as resources:
                if hasattr(provider, 'acquire'):
                    resources.callback(provider.acquire())
                def populate():
                    provider.mkdir('Library')
                    provider.mkdir('Library/Folder')
                    for i in range(40):
                        provider.create_file(f'Library/Folder/Note {i:02}.md', BytesIO(b'# Synthetic note'))
                    for i in range(4):
                        provider.mkdir(f'Library/Folder/Child {i}')
                        provider.create_file(f'Library/Folder/Child {i}/Child {i}.md', BytesIO(b'# Landing'))
                await asyncio.to_thread(populate)
                for variant in config['order']:
                    assert variant in ('legacy', 'recycled')
                    legacy = patch.object(VaultBrowser, 'new_panel_rows',
                        lambda owner: toga.Box(style=Pack(direction=COLUMN))) if variant == 'legacy' else nullcontext()
                    view = provider if hasattr(provider, 'reopen') else LocalFiles(root)
                    with legacy:
                        owner = await open_vault(app, view, 'Library', 'documents')
                    owner.sidebar.show_sidebar()
                    await self.settle(owner)
                    assert bool(getattr(owner.rows, 'recycled', False)) == (variant == 'recycled')
                    for cold in (True, False):
                        await self.measure(owner, storage, variant, cold, report)
                    if variant == 'recycled':
                        report['interaction_storage'] = storage
                        await self.interactions(owner, report)
                    else:
                        owner.dispose()
                report['cases'].append('paired_folder_rows_' + storage)
        atomic_json(Path(self.paths.cache) / 'notes-performance-progress.json', dict(phase='complete'))


def main():
    return NotesRowsPerformanceProbe('Notes Row Performance QA', 'io.github.ispaure.logisticsnotebookqa')
