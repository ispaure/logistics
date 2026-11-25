"""Bounded comparison of ordinary replacements and rclone on a removable card."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory, mkdtemp
from time import monotonic
import traceback
from uuid import uuid4
from zipfile import ZipFile

import toga
from toga.style import Pack

from commonUtils.testing.stages import TestStage
from . import start_native_check

TEST_STAGE = TestStage.REGRESSION
MIB = 1024 * 1024
COUNT = 10
FILE_MIB = 24
NAMES = tuple(f'fixture-{index:02}.bin' for index in range(COUNT))


def removable_directory(activity):
    from android.content import Context

    manager = activity.getSystemService(Context.STORAGE_SERVICE)
    choices = []
    for folder in activity.getExternalFilesDirs(None):
        if folder is None:
            continue
        volume = manager.getStorageVolume(folder)
        if volume is not None and volume.isRemovable() and str(volume.getState()) == 'mounted':
            choices.append((Path(str(folder.getCanonicalPath())), str(volume.getUuid())))
    if len(choices) > 1:
        raise ValueError('Connect only the removable SD card under test.')
    return choices[0] if choices else None


def snapshot(root):
    usage = shutil.disk_usage(root)
    paths = (root, *root.iterdir())
    return dict(used=usage.used, free=usage.free, owned=sum(path.stat().st_blocks * 512 for path in paths))


def seconds(start):
    return round(monotonic() - start, 4)


def check_stop(stop):
    if stop.exists():
        raise OSError('Stopped after Android reported a new SD controller error.')


def write_fixture(path, block, copies, stop, *, durable=False):
    check_stop(stop)
    start = monotonic()
    with path.open('xb', buffering=0) as stream:
        for index in range(copies):
            if index % 4 == 0:
                check_stop(stop)
            if stream.write(block) != len(block):
                raise OSError('Short write to ' + path.name)
        written = seconds(start)
        if durable:
            os.fsync(stream.fileno())
        flushed = seconds(start)
    return dict(write=written, fsync=round(flushed - written, 4), close=round(seconds(start) - flushed, 4))


def verify_file(path, expected, mibs):
    with path.open('rb') as stream:
        if path.stat().st_size != mibs * MIB or file_digest(stream, 'sha256').hexdigest() != expected:
            raise OSError('Read-back mismatch in ' + path.name)


def seed_targets(root, stop):
    root.mkdir()
    for name in NAMES:
        write_fixture(root / name, b'S' * MIB, 1, stop)


def direct_replacements(root, stop, block, expected, *, workers, durable):
    def replace(name):
        partial = root / (name + '.partial')
        sample = write_fixture(partial, block, FILE_MIB, stop, durable=durable)
        check_stop(stop)
        start = monotonic()
        partial.replace(root / name)
        return dict(name=name, rename=seconds(start), **sample)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        timings = list(pool.map(replace, NAMES))
    for name in NAMES:
        verify_file(root / name, expected, FILE_MIB)
    return timings


async def rclone_replacements(root, cache, stop, block, expected):
    from commonUtils.runtime.resources.documents import LocalDocuments
    from features.rclone.mobile.cloud import CloudClient

    client = CloudClient()
    root = root.resolve(strict=True)
    with TemporaryDirectory(prefix='sd-fixture-', dir=cache) as directory:
        fixture = Path(directory).resolve()
        source = fixture / 'source'
        source.mkdir()
        for name in NAMES:
            await asyncio.to_thread(write_fixture, source / name, block, FILE_MIB, stop)
        package = fixture / 'Synthetic.zip'
        with ZipFile(package, 'w') as archive:
            archive.writestr('StorageQA.txt', '[StorageQA]\ntype=memory\n')
        await asyncio.to_thread(client.import_package, LocalDocuments(), package, '', remember=False)
        identity = await asyncio.to_thread(client.connection_identity, 'StorageQA')

        async def sync(folder, push):
            task = asyncio.create_task(asyncio.to_thread(client.request, 'mirror_sync', remote='StorageQA',
                path='payload', local_path=str(folder), identity=identity, run=uuid4().hex, push=push))
            while not task.done():
                if stop.exists():
                    await asyncio.to_thread(client.cancel)
                    break
                await asyncio.wait((task,), timeout=.25)
            return await task

        await sync(source, True)
        check_stop(stop)
        start = monotonic()
        copied = await sync(root, False)
        elapsed = seconds(start)
        if copied != COUNT or set(path.name for path in root.iterdir()) != set(NAMES):
            raise OSError(f'rclone returned {copied} replacements or left additional entries.')
        for name in NAMES:
            await asyncio.to_thread(verify_file, root / name, expected, FILE_MIB)
        return dict(copied=copied, sync_seconds=elapsed)


async def verify_recoverable_publication(card, cache, stop, block, expected, stage, result):
    from commonUtils.persistence import atomic_write_json
    from commonUtils.runtime.resources.local import LocalFiles
    from features.notebooks.notebook import Notebook
    from features.notebooks.storage import NotebookDocument
    from services.documents.storage import DocumentResource, stage_local_document_export

    pending = cache / 'boox-sd-recovery-fixture.json'
    journal = card / '.logistics-sd-recovery-v1'
    target_name = 'Notebook.rmdoc'
    if not pending.exists():
        stage('Preparing an interrupted RMDOC replacement')
        scratch = Path(mkdtemp(prefix='logistics-sd-recovery-', dir=card))
        txn = journal / 'replace-interruption-fixture'
        txn.mkdir(parents=True)
        target = scratch / target_name
        old = Notebook.new('Previous notebook').to_bytes()
        target.write_bytes(old)
        partial = scratch / ('.save-' + uuid4().hex + '.rmdoc')
        partial.write_bytes(Notebook.new('Interrupted draft').to_bytes())
        info = partial.stat()
        atomic_write_json(txn / 'record.json', dict(target=str(target.relative_to(card)),
            partial=str(partial.relative_to(card)), size=info.st_size, mtime=info.st_mtime_ns))
        target.rename(txn / 'old')
        atomic_write_json(pending, dict(scratch=str(scratch), old=sha256(old).hexdigest(), partial=str(partial)))
        (cache / 'boox-sd-restart').touch()
        await asyncio.Event().wait()  # The host force-stops only the QA package at this boundary.

    fixture = json.loads(pending.read_text())
    scratch = Path(fixture['scratch'])
    if scratch.parent != card or not scratch.name.startswith('logistics-sd-recovery-'):
        raise ValueError('Unexpected SD test fixture location.')
    try:
        stage('Restoring the previous RMDOC after process restart')
        with DocumentResource(LocalFiles(scratch), target_name, max_bytes=32 * MIB) as resource:
            recovered = await asyncio.to_thread(resource.read)
            if sha256(recovered).hexdigest() != fixture['old']:
                raise OSError('An interrupted save did not recover the previous notebook.')
            if any(journal.iterdir()):
                raise OSError('Notebook recovery left a transaction on the card.')
            result['interrupted_rmdoc_recovered'] = True
            Path(fixture['partial']).unlink()
            before = snapshot(scratch)
            for index in range(3):
                document = NotebookDocument(Notebook.new(f'Updated notebook {index}'), resource=resource)
                await asyncio.to_thread(document.save)
            if Notebook.read(resource.read()).name != 'Updated notebook 2':
                raise OSError('The notebook did not reopen after successive saves.')
            streamed = Notebook.new('Streamed notebook').to_bytes()
            with stage_local_document_export(scratch / target_name, expected_revision=resource.revision) as stream:
                stream.write(streamed)
            if Notebook.read(resource.read()).name != 'Streamed notebook':
                raise OSError('The streamed notebook target did not reopen.')
            saved = snapshot(scratch)
            result['editor_unexplained_bytes'] = saved['used'] - before['used'] - (saved['owned'] - before['owned'])
            if result['editor_unexplained_bytes'] != 0:
                raise OSError('RMDOC replacements left space charged to the old files.')
        check_stop(stop)
        stage('Running ten embedded rclone replacements')
        before = snapshot(scratch)
        root = scratch / 'replacements'
        await asyncio.to_thread(seed_targets, root, stop)
        replacement = await rclone_replacements(root, cache, stop, block, expected)
        await asyncio.to_thread(shutil.rmtree, root)
        after = snapshot(scratch)
        replacement['unexplained_bytes'] = after['used'] - before['used'] - (after['owned'] - before['owned'])
        result['rclone'] = replacement
        if replacement['unexplained_bytes'] != 0 or any(journal.iterdir()):
            raise OSError('rclone replacements left space charged or a pending transaction.')
    finally:
        await asyncio.to_thread(shutil.rmtree, scratch)


class BooxSDWriteProbe(toga.App):
    def startup(self):
        self.status = toga.Label('Waiting for a removable SD card.')
        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = toga.Box(children=[self.status], style=Pack(margin=24))
        self.main_window.show()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def probe(self):
        cache = Path(self.paths.cache)
        stop = cache / 'boox-sd-stop'
        result = dict(success=False, phases=[])

        def stage(name):
            self.status.text = name
            (cache / 'boox-sd-progress.json').write_text(json.dumps(dict(stage=name, **result)))

        try:
            activity = self._impl.native
            activity.getWindow().addFlags(128)  # FLAG_KEEP_SCREEN_ON, for this QA app only.
            stage('Waiting for the removable SD card')
            for _ in range(180):
                check_stop(stop)
                if selected := removable_directory(activity):
                    break
                await asyncio.sleep(1)
            else:
                raise OSError('No writable removable SD card was mounted.')
            card, result['volume'] = selected
            if shutil.disk_usage(card).free < 4 * 1024 * MIB:
                raise OSError('The SD probe needs 4 GiB free for a bounded test.')
            block = os.urandom(MIB)
            digest = sha256()
            for _ in range(FILE_MIB):
                digest.update(block)
            expected = digest.hexdigest()
            result['free_before'] = shutil.disk_usage(card).free
            if (cache / 'boox-sd-recovery').exists():
                await verify_recoverable_publication(card, cache, stop, block, expected, stage, result)
                result['free_after'] = shutil.disk_usage(card).free
                check_stop(stop)
                result['success'] = True
                stage('SD recovery and replacements verified')
                (cache / 'boox-sd-write-result.json').write_text(json.dumps(result, indent=2))
                return
            with TemporaryDirectory(prefix='logistics-sd-probe-', dir=card) as directory:
                scratch = Path(directory)
                for label, workers, durable in (('serial replace', 1, False), ('parallel replace', 10, False),
                        ('parallel replace with fsync', 10, True), ('embedded rclone Pull', 10, False)):
                    check_stop(stop)
                    stage(label)
                    before = snapshot(scratch)
                    root = scratch / 'replacements'
                    await asyncio.to_thread(seed_targets, root, stop)
                    start = monotonic()
                    if label == 'embedded rclone Pull':
                        observations = await rclone_replacements(root, cache, stop, block, expected)
                    else:
                        timings = await asyncio.to_thread(direct_replacements, root, stop, block, expected,
                                                           workers=workers, durable=durable)
                        observations = dict(files=timings)
                    elapsed = seconds(start)
                    replaced = snapshot(root)
                    await asyncio.to_thread(shutil.rmtree, root)
                    after = snapshot(scratch)
                    unexplained = after['used'] - before['used'] - (after['owned'] - before['owned'])
                    result['phases'].append(dict(name=label, workers=workers, file_mib=FILE_MIB,
                        seconds=elapsed, before=before, replaced=replaced, after=after,
                        unexplained_bytes=unexplained, **observations))
                    if unexplained > 16 * MIB:
                        raise OSError('Unexpected space stayed allocated after removing the synthetic files.')
            result['free_after'] = shutil.disk_usage(card).free
            check_stop(stop)
            result['success'] = True
            stage('SD write comparisons complete')
        except Exception:
            result['error'] = traceback.format_exc()
            stage('SD write probe stopped')
        (cache / 'boox-sd-write-result.json').write_text(json.dumps(result, indent=2))


def main():
    return BooxSDWriteProbe('Logistics SD QA', 'io.github.ispaure.logisticssdqa')
