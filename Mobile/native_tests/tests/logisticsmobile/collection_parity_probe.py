"""Separate-app native collection probe; synthetic credentials and archives only."""
import asyncio
import base64
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import traceback
from zipfile import ZipFile

from commonUtils.runtime.document_access import LocalDocuments
from features.comics.mobile.index import CollectionIndex
from features.rclone.localcrypt.mobile.resources import CryptFiles, encrypted_document
from logisticsmobile.app import LogisticsMobile
from .fixtures import capture_window

BUNDLE = 'io.github.ispaure.logisticscollectionprobe'


def resources(reader):
    with reader.source.open_archive(reader.name) as archive:
        return {info.filename: sha256(archive.read(info)).hexdigest()
                for info in archive.infolist() if not info.is_dir() and Path(info.filename).name.lower() != 'comicinfo.xml'}


class CollectionProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'collection-validation-v1'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        output = self.private_root / 'evidence'
        output.mkdir(exist_ok=True)
        result = dict(success=False, target='ipad' if sys.platform == 'ios' else 'android',
                      cases=[], scope='Targeted native collection probe in a separate app with synthetic data; not release or physical-device certification.')
        try:
            from importlib.resources import files
            result['source'] = json.loads(files('logisticsmobile').joinpath('source.json').read_text())
            restart = output / 'restart.json'
            if restart.exists():
                result.update(json.loads(restart.read_text()))
                result['success'] = False
                self.show_library()
                catalog = self.reader_manager().catalog
                opened = catalog.library_store.open
                def unexpected_archive_read(*args, **kwargs):
                    raise AssertionError('Restart reread an unchanged archive')
                catalog.library_store.open = unexpected_archive_read
                try:
                    await catalog.metadata_task
                finally:
                    catalog.library_store.open = opened
                assert catalog.metadata_index.page('author 259')[1] == 1
                assert catalog.metadata_index.page('Large collection')[1] == 260
                assert len(catalog.library_row_buttons) == 50
                assert getattr(self, 'private_comic_batch', None) is None
                result['cases'].append('process_restart_reuses_persisted_index_without_archive_reads')
                result['success'] = True
                restart.unlink()
                return
            self.show_cloud()
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
            fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
            self.cloud_client.request('import', package=fixture['package'], password='synthetic-session-password', package_name='Synthetic.zip', session_only=True)
            await asyncio.sleep(.1)
            provider = CryptFiles(self.private_root / 'PrivateBatchFixture', self.cloud_client, 'Secret')
            provider._physical('nested', directory=True).mkdir()
            for name, sample in [('one.cbz', 'plain.cbz'), ('nested/two.cbz', 'encrypted.cbz')]:
                provider._physical(name).write_bytes(base64.b64decode(fixture['copies'][sample]['ciphertext']))
            # Existing bridge binaries accept text/Markdown encode; encrypted
            # payloads are independent of their separately encrypted names.
            provider.create_file('settings.md', BytesIO(b'[LogisticsZIP]\narchive_password=synthetic-archive-password\n'))
            provider._physical('settings.md').rename(provider._physical('remoteConfig.ini'))

            async def open_batch():
                await self.show_files()
                self.file_roots['LocalCrypt: Batch probe'] = provider
                self.update_file_locations()
                await self.browser_file_location(('LocalCrypt: Batch probe', ''))
                self.file_selection.value = 'Select an item…'
                await self.edit_local_comic_folder()
                assert self.private_comic_batch is not None, self.file_action_status.text
                assert self.private_comic_batch.view is not None, self.file_action_status.text
                return self.private_comic_batch

            plan = await open_batch()
            assert len(plan.documents) == 2
            assert all(not hasattr(document, 'source') for document in plan.documents)
            original = {}
            for row in plan.entries:
                copies, key = encrypted_document(provider, row['path'])
                original[row['path']] = resources(copies.open(key))
            view = plan.view
            view.metadata_inputs['Writer'].value = 'Private batch secret writer'
            view.metadata_switches['Writer'].value = True
            await view.metadata_apply(None)
            assert '2 saved' in view.metadata_status.text, view.metadata_status.text
            for row in plan.entries:
                copies, key = encrypted_document(provider, row['path'])
                reader = copies.open(key)
                assert reader.comic.info.get_field('Writer') == 'Private batch secret writer'
                assert resources(reader) == original[row['path']]
            result['cases'].append('recursive_private_plain_and_inner_encrypted_verified_publication')
            await asyncio.sleep(.7)
            await capture_window(self, output / 'private-batch.png')

            # Cancellation is observed between publications and retries use the
            # successful file's updated baseline rather than the initial snapshot.
            publish = plan.publish
            def once(reader, changes, **kwargs):
                updated = publish(reader, changes, **kwargs)
                plan.cancel.set()
                return updated
            plan.publish = once
            completed, failures = await asyncio.to_thread(plan.apply, {'Publisher': 'Cancelled batch publisher'})
            assert len(completed) == 1 and not failures, (completed, failures)
            plan.publish = publish
            plan.cancel.clear()
            completed, failures = await asyncio.to_thread(plan.apply, {'Publisher': 'Retry publisher'})
            assert len(completed) == 2 and not failures
            result['cases'].append('private_batch_cancel_after_current_and_retry_baselines')

            first = provider._physical(plan.entries[0]['path']).read_bytes()
            second_path = provider._physical(plan.entries[1]['path'])
            second = second_path.read_bytes()
            second_path.write_bytes(second + b'changed')
            try:
                await asyncio.to_thread(plan.apply, {'Title': 'Must not publish'})
                raise AssertionError('Changed baseline was accepted')
            except ValueError:
                pass
            assert provider._physical(plan.entries[0]['path']).read_bytes() == first
            second_path.write_bytes(second)
            result['cases'].append('private_batch_all_file_preflight_rejects_conflicts')

            field = view.metadata_inputs['Writer']
            self.release_disposable_resources()
            assert plan.closed and not plan.documents and not plan.entries
            assert field.value == '' and not view.metadata_inputs
            assert self.private_comic_batch is None
            await view.metadata_apply(None)  # Retired callback cannot publish.
            result['cases'].append('private_batch_suspend_erases_metadata_forms_and_callbacks')
            plan = await open_batch()
            from threading import Event
            entered, proceed = Event(), Event()
            publish = plan.publish
            before = {row['path']: provider._physical(row['path']).read_bytes() for row in plan.entries}
            def delayed(reader, changes, **kwargs):
                entered.set()
                if not proceed.wait(10):
                    raise AssertionError('Retirement test did not release worker')
                return publish(reader, changes, **kwargs)
            plan.publish = delayed
            worker = asyncio.create_task(asyncio.to_thread(plan.apply, {'Writer': 'Retired worker must not publish'}))
            for _ in range(200):
                if entered.is_set():
                    break
                await asyncio.sleep(.05)
            assert entered.is_set()
            self.screen_privacy.conceal()
            proceed.set()
            await worker
            self.screen_privacy.reveal()
            assert plan.closed
            assert all(provider._physical(path).read_bytes() == data for path, data in before.items())
            result['cases'].append('concealed_private_batch_worker_cannot_publish')
            plan = await open_batch()
            view = plan.view
            field = view.metadata_inputs['Writer']
            self.cloud_client.request('import', package=fixture['package'], password='synthetic-session-password', package_name='Synthetic.zip', session_only=True)
            await asyncio.sleep(.3)
            assert plan.closed and field.value == '' and not plan.documents
            result['cases'].append('private_batch_credentials_revoke_immediately')

            # Real imported archives beyond the former first-200 cap.
            self.show_library()
            catalog = self.reader_manager().catalog
            await catalog.metadata_task
            def import_many():
                source = self.private_root / 'ordinary-source.cbz'
                for number in range(260):
                    from .reader_parity_probe import image_bytes
                    with ZipFile(source, 'w') as archive:
                        archive.writestr('page.png', image_bytes(b'\xff\0\0\xff'))
                        archive.writestr('ComicInfo.xml', f'<ComicInfo><Writer>Ordinary author {number}</Writer><Tags>Large collection</Tags></ComicInfo>')
                    catalog.library_store.import_book(LocalDocuments(), source)
            await asyncio.to_thread(import_many)
            catalog.refresh_library()
            await catalog.metadata_task
            assert catalog.metadata_index.page('Large collection')[1] == 260
            assert len(catalog.library_row_buttons) == 50
            catalog.page_library(1)
            assert catalog.library_offset == 50 and len(catalog.library_row_buttons) == 50
            catalog.library_search.value = 'author 259'
            catalog.filter_library()
            assert len(catalog.library_row_buttons) == 1, catalog.library_page_status.text
            assert catalog.metadata_index.page('author 259')[1] == 1
            result['cases'].append('native_260_import_metadata_search_and_50_row_paging')
            await asyncio.sleep(.7)
            await capture_window(self, output / 'large-library.png')
            recreated = CollectionIndex(catalog.metadata_index.path)
            def must_not_open(record):
                raise AssertionError('Unchanged archive was reread')
            def signature(record):
                info = catalog.library_store.path(record['id'], '.cbz').stat()
                return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
            await asyncio.to_thread(recreated.scan, catalog.imported_records, signature=signature, load=must_not_open)
            assert recreated.page('author 259')[1] == 1
            result['cases'].append('persistent_incremental_index_reopens_without_archive_reads')
            # Search all app-private persisted bytes, including SQLite/recovery.
            for path in self.private_root.rglob('*'):
                if path.is_file():
                    data = path.read_bytes()
                    assert b'Private batch secret writer' not in data, path.name
                    assert b'nested/two.cbz' not in data, path.name
            result['cases'].append('private_batch_metadata_absent_from_persisted_index_and_recovery')
            result['imports'] = 260
            result['page_size'] = 50
            result['success'] = True
            restart.write_text(json.dumps(result))
            result['awaiting_restart'] = True
        except Exception:
            result['error'] = traceback.format_exc()
            traceback.print_exc()
        finally:
            (output / 'result.json').write_text(json.dumps(result, indent=2))
            print('COLLECTION_PROBE_RESULT=' + json.dumps(result), flush=True)
            await asyncio.sleep(.2)
            os._exit(0 if result['success'] else 1)


def main():
    return CollectionProbe('Logistics Collection Probe', BUNDLE)
