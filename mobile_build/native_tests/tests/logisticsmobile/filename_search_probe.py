"""Matched filename searches through the native Files list and action callbacks."""
import asyncio
import json
import os
from pathlib import Path
from threading import Event
from time import monotonic
import traceback

import toga

from commonUtils.testing.stages import TestStage
from services.documents.locations import CollectionFiles
from services.directory_index import acquire

TEST_STAGE = TestStage.REGRESSION
from features.rclone.localcrypt.mobile.resources import CryptFiles
from features.rclone.localcrypt.path_batches import native_path_entries
from mobile.app import LogisticsMobile
from mobile.browser_ui import FileBrowser

BUNDLE = 'io.github.ispaure.logisticsstorageqa'
QUERY = 'qa-search-sentinel'
TARGET = QUERY + '.txt'
PRIVATE_RENAMED = QUERY + '-private-renamed-6633.txt'


class SearchProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'filename-search-fixtures'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.run_probe())

    async def wait(self, condition):
        async with asyncio.timeout(150):
            while not condition():
                await asyncio.sleep(.005)

    def make_tree(self, local, crypt, folders, count):
        for index in range(folders):
            folder = f'folder-{index:03}'
            names = [f'document-{number:04}.txt' for number in range(count)]
            if index == 0:
                names[0] = TARGET
            (local.root / folder).mkdir(parents=True)
            physical = crypt._physical(folder, directory=True)
            physical.mkdir(parents=True)
            encoded = native_path_entries(crypt.client, crypt.remote, crypt.identity,
                                          [(name, False) for name in names], check=crypt._access.check, encode=True)
            for name, cipher in zip(names, encoded, strict=True):
                (local.root / folder / name).touch()
                (physical / cipher).touch()
        for provider in (local, crypt):
            provider.mkdir('pending-view')
        (local.root / 'pending-view/next-view.txt').touch()
        crypt._physical('pending-view/next-view.txt').touch()

    async def sample(self, browser, provider, cold, phases):
        browser.set_entries(provider, '', await asyncio.to_thread(provider.list, ''),
                            location=('fixture', ''))
        browser.open_search()
        actions = []
        browser.on_item_actions = lambda row: actions.append(row['path'])
        phases.clear()
        start = monotonic()
        browser.search.value = QUERY
        await self.wait(lambda: any(row.entry.payload['path'] == 'folder-000/' + TARGET
                                    for row in browser.native_list.data))
        row = next(row for row in browser.native_list.data if row.entry.payload['path'].endswith('/' + TARGET))
        await browser._select_row(row)
        assert actions == ['folder-000/' + TARGET], actions
        first = monotonic() - start
        await self.wait(lambda: browser.page_label.text == '1 matches' and not browser.searching)
        complete = monotonic() - start
        result = dict(cold=cold, first=first, completion=complete,
                      worker_phases=dict(phases))
        browser.close_search()
        await self.wait(lambda: not browser.searching)
        return result

    async def cancellation(self, browser, provider):
        entered, release, retired = Event(), Event(), Event()
        search = browser.resource_search

        def hold(*args, **kwargs):
            cancelled = kwargs['cancelled']
            callback = kwargs['progress']

            def publish(result):
                if result.rows and not entered.is_set():
                    callback(result)
                    entered.set()
                    if not release.wait(20):
                        raise AssertionError('Cancellation probe never released')
                    # Exercise a late callback even with a cancelled worker.
                    callback(result)
                else:
                    callback(result)

            kwargs['progress'] = publish
            try:
                return search(*args, **kwargs)
            finally:
                if cancelled():
                    retired.set()

        browser.resource_search = hold
        browser.open_search()
        try:
            browser.search.value = QUERY
            await self.wait(entered.is_set)
            start = monotonic()
            browser.close_search()
            next_rows = await asyncio.to_thread(provider.list, 'pending-view')
            browser.set_entries(provider, 'pending-view', next_rows,
                                location=('fixture', 'pending-view'))
            actions = []
            browser.on_item_actions = lambda row: actions.append(row['path'])
            await browser._select_row(browser.native_list.data[0])
            elapsed = monotonic() - start
            assert actions == ['pending-view/next-view.txt'], actions
            release.set()
            await self.wait(retired.is_set)
            await asyncio.sleep(.08)
            assert [row.entry.payload['path'] for row in browser.native_list.data] == actions
            return elapsed
        finally:
            release.set()
            browser.resource_search = search

    async def cold_cancellation(self, provider, database):
        from mobile.local_search import LocalSearch
        if provider.private:
            provider = provider.reopen()
            provider._directory_index.folder = database.with_suffix('')
        lease = acquire(database) if not provider.private else None
        search = LocalSearch(database)
        browser = FileBrowser(local_search=search)
        self.main_window.content = browser.widget
        try:
            browser.set_entries(provider, '', await asyncio.to_thread(provider.list, ''), location=('fixture', ''))
            return await self.cancellation(browser, provider)
        finally:
            await browser.close()
            search.cache.close()
            if lease is not None:
                lease.close()

    async def verify_rename(self, browser, provider):
        old = 'folder-000/' + TARGET
        moved = 'folder-000/' + (PRIVATE_RENAMED if provider.private else QUERY + '-local-renamed.txt')
        await asyncio.to_thread(provider.rename, old, moved)
        browser.set_entries(provider, '', await asyncio.to_thread(provider.list, ''), location=('fixture', ''))
        browser.open_search()
        browser.search.value = QUERY
        await self.wait(lambda: browser.page_label.text == '1 matches' and not browser.searching
                        and [row.entry.payload['path'] for row in browser.native_list.data] == [moved])
        actions = []
        browser.on_item_actions = lambda row: actions.append(row['path'])
        await browser._select_row(browser.native_list.data[0])
        assert actions == [moved]
        return 'localcrypt_rename_refresh' if provider.private else 'local_rename_refresh'

    async def verify_lock(self, browser, provider):
        self.file_browser = browser
        search, release, queued = browser.resource_search, Event(), Event()

        def delay(*args, **kwargs):
            callback = kwargs['progress']

            def publish(result):
                if result.rows and not queued.is_set():
                    queued.set()
                    if not release.wait(20):
                        raise AssertionError('Lock probe never released')
                callback(result)

            return search(*args, **dict(kwargs, progress=publish))

        browser.resource_search = delay
        try:
            old_row = browser.native_list.data[0]
            browser.query_changed()
            await self.wait(queued.is_set)
            await self.cloud_controller().lock_cloud()
            assert browser.closed and not provider._directory_index.rows
            release.set()
            await browser.close()
            assert not browser.native_list.data and not browser.search.value
            assert PRIVATE_RENAMED not in browser.page_label.text
            await browser._select_row(old_row)
            assert provider.closed
        finally:
            release.set()
            browser.resource_search = search

    async def run_probe(self):
        result = dict(success=False, samples=[])
        try:
            from importlib.resources import files
            result['source'] = json.loads(files('mobile').joinpath('source.json').read_text())
            self.show_cloud()
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
            fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
            self.cloud_client.request('import', package=fixture['package'],
                                      password='synthetic-session-password', package_name='Synthetic.zip',
                                      session_only=True)
            self.main_window.content = toga.Box()
            from mobile.local_search import LocalSearch
            for size, folders, count in [('small', 4, 40), ('large', 20, 300)]:
                local = CollectionFiles(self.private_root / (size + '-local'))
                crypt = CryptFiles(self.private_root / (size + '-crypt'), self.cloud_client, 'Secret')
                await asyncio.to_thread(self.make_tree, local, crypt, folders, count)
                for source, provider in [('Local', local), ('LocalCrypt', crypt)]:
                    database = self.private_root / 'Cache' / f'{size}-{source}.sqlite3'
                    lease = acquire(database) if not provider.private else None
                    search = LocalSearch(database)
                    view = FileBrowser(local_search=search)
                    self.main_window.content = view.widget
                    phases = {}
                    def timer(owner, method, label):
                        original = getattr(owner, method)
                        def measured(*args, **kwargs):
                            start = monotonic()
                            try:
                                return original(*args, **kwargs)
                            finally:
                                phases[label] = phases.get(label, 0) + monotonic() - start
                        setattr(owner, method, measured)
                    from commonUtils.search import providers
                    from features.rclone.localcrypt.mobile import resources
                    match, format_date = providers.matches_name, resources._modified_time
                    timer(providers, 'matches_name', 'filtering')
                    timer(resources, '_modified_time', 'metadata_formatting')
                    timer(view, 'set_tree', 'publication')
                    timer(search, 'search', 'search_worker')
                    timer(provider, 'list', 'provider_list')
                    if provider.private:
                        timer(provider._directory_index, '_fingerprint', 'index_validation')
                        timer(provider, '_note_decode', 'decrypt')
                    else:
                        timer(search, '_prepare', 'index_prepare')
                    for cold in (True, False, False):
                        sample = await self.sample(view, provider, cold, phases)
                        result['samples'].append(dict(sample, size=size, source=source, files=folders*count+1))
                    providers.matches_name, resources._modified_time = match, format_date
                    for sample in result['samples'][-2:]:
                        view.set_entries(provider, '', await asyncio.to_thread(provider.list, ''), location=('fixture', ''))
                        sample['cancel_to_next_action'] = await self.cancellation(view, provider)
                    result['samples'][-3]['cancel_to_next_action'] = await self.cold_cancellation(
                        provider, database.with_name('cancel-' + database.name))
                    self.main_window.content = view.widget
                    if size == 'large':
                        result.setdefault('cases', []).append(await self.verify_rename(view, provider))
                        if provider.private:
                            await self.verify_lock(view, provider)
                            result['cases'].append('lock_retires_queued_private_results')
                            for path in self.private_root.rglob('*'):
                                if path.is_file():
                                    assert PRIVATE_RENAMED.encode() not in path.read_bytes()
                            assert not database.exists()
                            result['cases'].append('private_rename_absent_from_persisted_plaintext_and_ordinary_index')
                    await view.close()
                    search.cache.close()
                    if lease is not None:
                        lease.close()
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
            traceback.print_exc()
        finally:
            (Path(self.paths.cache) / 'filename-search-result.json').write_text(json.dumps(result, indent=2))
            await asyncio.sleep(.5)
            os._exit(0 if result['success'] else 1)


def main():
    return SearchProbe('Filename Search QA', BUNDLE)
