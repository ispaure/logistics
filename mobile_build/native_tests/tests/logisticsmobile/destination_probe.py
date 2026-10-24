"""Disposable native destination/hidden-row acceptance with external tap checkpoints."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from mobile.app import LogisticsMobile

BUNDLE = 'io.github.ispaure.logisticsdestinationqa'


class DestinationProbe(LogisticsMobile):
    hidden_only = False

    def startup(self):
        import logging
        logging.getLogger().addHandler(logging.FileHandler(Path(self.paths.cache) / 'destination-python.log'))
        self.storage_root = Path(self.paths.cache) / ('destinations-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_destination_started', False):
            self._destination_started = True
            self.loop.create_task(self.check_destinations())

    def state(self, phase, **kwargs):
        data = {'phase': phase, 'backend': type(self._impl).__module__, **kwargs}
        (Path(self.paths.cache) / 'destination-state.json').write_text(json.dumps(data))

    async def wait(self, condition, timeout=300):
        for _ in range(timeout * 10):
            if condition():
                return
            await asyncio.sleep(.1)
        raise TimeoutError('Native interaction did not complete.')

    def check_native_hidden_colors(self, browser, roles=None):
        roles = roles or {'.HiddenParent': 'muted', '.Hidden.txt': 'muted', 'Flagged.txt': 'muted', 'Ordinary.txt': 'text'}
        native = browser.native_list._impl.native
        if type(self._impl).__module__.startswith('toga_iOS.'):
            found = set()
            for cell in native.visibleCells:
                label = str(cell.textLabel.text)
                if label not in roles:
                    continue
                role = roles[label]
                expected = browser.native_list.appearance.apple_color(role).resolvedColorWithTraitCollection(native.traitCollection)
                actual = cell.textLabel.textColor.resolvedColorWithTraitCollection(native.traitCollection)
                selected = cell.textLabel.highlightedTextColor.resolvedColorWithTraitCollection(native.traitCollection)
                assert actual.isEqual(expected), (label, str(actual), str(expected))
                assert selected.isEqual(expected), (label, 'selected color')
                found.add(label)
            assert found == set(roles), found
        else:
            from android.graphics import Color
            dark = native.getResources().getConfiguration().uiMode & 0x30 == 0x20
            palette = browser.native_list.appearance.palette(dark)
            found = set()
            def labels(view):
                if hasattr(view, 'getText') and hasattr(view, 'getCurrentTextColor'):
                    yield view
                if hasattr(view, 'getChildCount'):
                    for index in range(view.getChildCount()):
                        yield from labels(view.getChildAt(index))
            for index in range(native.getChildCount()):
                for label in labels(native.getChildAt(index)):
                    title = str(label.getText())
                    if title not in roles:
                        continue
                    role = roles[title]
                    expected = Color.parseColor(palette[role])
                    assert label.getCurrentTextColor() == expected, (title, dark)
                    native.selectRow(native.getFirstVisiblePosition() + index)
                    if role == 'muted':
                        assert label.getCurrentTextColor() == expected, (title, 'selected color')
                    native.selectRow(-1)
                    found.add(title)
            assert found == set(roles), found

    async def check_destinations(self):
        report = dict(success=False, cases=[], backend=type(self._impl).__module__)
        try:
            self.show_cloud(present=False)
            restore = getattr(self, 'cloud_restore_task', None)
            if restore is not None:
                await restore
            if not self.hidden_only:
                picker = self.editor_picker()
                await picker.show_text_destination('Source.md', b'# Native destination fixture')
                await asyncio.sleep(.5)
                root = picker.editor_provider(picker.save_as_storage.value).root
                self.state('save-ui', instructions='Tap New folder, enter Native folder, Create; enter Native saved; Save here.')
                await self.wait(lambda: (root / 'Native folder/Native saved.md').is_file())
                await self.wait(lambda: picker.save_as_data is None)
                assert (root / 'Native folder/Native saved.md').read_bytes() == b'# Native destination fixture'
                assert self.private_sessions.active.crypt_reader.name == 'Native saved.md'
                report['cases'].append('native-taps-new-folder-basename-save-reopen')
                self.clear_private_reader()
                await self.show_files(location=('Local files', ''))
                source = self.file_provider
                (source.root / 'Move me.txt').write_text('Native move bytes')
                (source.root / 'Destination').mkdir()
                from mobile.file_operations import FileOperationRequest
                await picker.show_destination('Move me.txt', FileOperationRequest('move', source, 'Move me.txt'))
                await asyncio.sleep(.4)
                await picker.browser_editor_location(('Local files', 'Destination'))
                self.state('move-ui', instructions='Tap Move here.')
                await self.wait(lambda: (source.root / 'Destination/Move me.txt').is_file())
                assert (source.root / 'Destination/Move me.txt').read_text() == 'Native move bytes'
                assert not (source.root / 'Move me.txt').exists()
                report['cases'].append('native-tap-browsed-move')
            await self.check_hidden(report)
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'destination-result.json').write_text(json.dumps(report, indent=2))
        self.state('complete', **report)

    async def check_hidden(self, report):
        await self.wait(lambda: not self.cloud_busy)
        await asyncio.sleep(.8)
        await self.show_files(location=('Local files', ''))
        from commonUtils.runtime.resources.local import LocalFiles
        fixture = self.private_root / 'HiddenFixture'
        fixture.mkdir()
        source = LocalFiles(fixture)
        (source.root / '.Hidden.txt').write_text('Synthetic hidden content')
        (source.root / 'Ordinary.txt').write_text('Synthetic normal content')
        (source.root / 'Flagged.txt').write_text('Synthetic provider metadata')
        (source.root / '.HiddenParent').mkdir()
        (source.root / '.HiddenParent/Ordinary child.txt').write_text('Ordinary child')
        for number in range(70):
            (source.root / f'Row {number:02}.txt').write_text('Synthetic row')
        await self.browse_files()
        await asyncio.sleep(.8)
        self.show_view(self.files_view, destination='files', route='browser', title='Hidden item QA')
        await asyncio.sleep(.8)
        browser = self.file_browser
        from commonUtils.runtime.resources.local import LocalFiles
        synthetic = LocalFiles(source.root)
        entry = synthetic.entry
        def flagged(path):
            row = entry(path)
            return dict(row, hidden=True) if row['name'] == 'Flagged.txt' else row
        synthetic.entry = flagged
        browser.set_entries(synthetic, '', synthetic.list(), location=('Local files', ''))
        await asyncio.sleep(.4)
        rows = {row.entry.label: row for row in browser.native_list.data}
        assert rows['.Hidden.txt'].hidden and not rows['Ordinary.txt'].hidden
        from commonUtils.search.providers import search_resources
        from commonUtils.runtime.browsing import provider_entries
        from commonUtils.ui.native_browser.recycled import hidden_entry
        result = await asyncio.to_thread(search_resources, source, '', 'txt')
        assert any(hidden_entry(entry) for entry in provider_entries(source, result.rows))
        from tests.logisticsmobile.fixtures import capture_window
        from commonUtils.search.indexed import IndexedLocalSearch
        # Fixture files were created after the app's first browser scan.
        # Use a fresh isolated index so this checks metadata propagation,
        # rather than an intentionally retained earlier filesystem snapshot.
        browser.local_search = IndexedLocalSearch(self.private_root / 'hidden-search.sqlite',
            eligible=lambda provider: provider is synthetic)
        await asyncio.to_thread(browser.local_search.prepare, synthetic, '', cancelled=lambda: False)
        for search in (search_resources, browser.local_search.search, browser.local_search.search):
            hits = await asyncio.to_thread(search, synthetic, '', 'txt')
            browser.set_entries(synthetic, '', hits.rows, location=('Local files', 'search'))
            await asyncio.sleep(.4)
            self.check_native_hidden_colors(browser, {'.Hidden.txt': 'muted', 'Flagged.txt': 'muted',
                'Ordinary.txt': 'text', 'Ordinary child.txt': 'text'})
        await capture_window(self, Path(self.paths.cache) / 'hidden-search.png')
        browser.set_entries(synthetic, '', synthetic.list(), location=('Local files', ''))
        await asyncio.sleep(.4)
        self.check_native_hidden_colors(browser)
        await capture_window(self, Path(self.paths.cache) / 'hidden-light.png')
        self.state('hidden-light', instructions='Inspect/list/scroll/select hidden and ordinary rows, then acknowledge.')
        command = Path(self.paths.cache) / 'destination-command'
        await self.wait(command.exists)
        command.unlink()
        browser.show_tiles()
        await asyncio.sleep(.4)
        await capture_window(self, Path(self.paths.cache) / 'hidden-tiles.png')
        self.state('hidden-tiles', instructions='Capture tiles and acknowledge.')
        await self.wait(command.exists)
        command.unlink()
        browser.show_list()
        await asyncio.sleep(.4)
        self.state('hidden-dark', instructions='Switch system appearance dark, inspect recycled rows, acknowledge.')
        await self.wait(command.exists)
        command.unlink()
        browser.native_list.refresh_palette()
        await asyncio.sleep(.3)
        self.check_native_hidden_colors(browser)
        await capture_window(self, Path(self.paths.cache) / 'hidden-dark.png')
        # Replacing the source exercises native reused rows losing hidden state.
        browser.set_entries(source, '', [source.entry('Ordinary.txt')], location=('Local files', ''))
        assert [row.hidden for row in browser.native_list.data] == [False]
        await asyncio.sleep(.4)
        self.check_native_hidden_colors(browser, {'Ordinary.txt': 'text'})
        report['cases'].append('native-hidden-list-tiles-search-theme-row-reuse')


def main():
    import sys
    if '--cancel-only' in sys.argv:
        from tests.logisticsmobile.destination_cancel_probe import DestinationCancelProbe
        return DestinationCancelProbe('Destination Cancel QA', BUNDLE)
    DestinationProbe.hidden_only = '--hidden-only' in sys.argv
    return DestinationProbe('Destination QA', BUNDLE)
