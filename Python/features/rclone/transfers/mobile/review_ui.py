"""Native presentation over the same review state and decisions as desktop."""
import asyncio
from hashlib import sha256
import json
from threading import Event, Thread
from uuid import uuid4

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from features.rclone.transfers.review import ReviewRequest, ReviewScan, unchanged, replace_changes
from features.rclone.transfers.transfer_options import TransferOptions, load_options, save_options


def native_scanner(client, job, local_path, options=TransferOptions(), cleanup_plan=lambda cancelled: {}):
    def scan(emit, cancelled):
        run, done = uuid4().hex, Event()
        def monitor():
            while not done.wait(.1):
                if cancelled():
                    client.cancel()
                    return
                try:
                    replace_changes(emit, client.request('mirror_review_progress', run=run)['changes'])
                except (OSError, ValueError, KeyError):
                    pass
        watcher = Thread(target=monitor, daemon=True)
        watcher.start()
        try:
            if cancelled():
                return ''
            cleanup = cleanup_plan(cancelled) if job['_push'] else {}
            result = client.request('mirror_review', remote=job['remote'], path=job['prefix'],
                identity=job['identity'], local_path=str(local_path.resolve()), run=run,
                push=job['_push'], decrypted=not job['crypt'], cleanup_paths=list(cleanup),
                **options.bridge_arguments(push=job['_push']))
            done.set()
            watcher.join()
            replace_changes(emit, [*result['changes'], *[('cleanup', label) for label, _ in cleanup.values()]])
            return sha256((result['fingerprint'] + json.dumps(cleanup, sort_keys=True)).encode()).hexdigest()
        finally:
            done.set()
            watcher.join()
            client.request('mirror_review_clear', run=run)
    return scan


class TransferReviewUI:
    def show_local_push(self, folder):
        if self.cloud_busy or getattr(self, 'transfer_busy', False):
            return
        remotes = sorted(self.loaded_remote_names(), key=str.casefold)
        box = toga.Box(style=Pack(direction=COLUMN, margin=12, flex=1))
        box.add(toga.Label('Push Local/' + folder, style=Pack(font_size=22)))
        box.add(toga.Label('Whole folder uses ' + folder + ': in the matching credential package.'))
        def whole(widget=None, **kwargs):
            self.begin_transfer_review(push=True, local_folder=folder)
        box.add(toga.Button('Push whole folder…', on_press=whole, style=Pack(height=44)))
        if remotes:
            destination = toga.Selection(items=remotes, style=Pack(height=44))
            preview = toga.Label('')
            def update(widget=None, **kwargs):
                preview.text = 'To: ' + destination.value + ':' + folder
            destination.on_change = update
            update()
            def specific(widget=None, **kwargs):
                self.begin_transfer_review(push=True, local_folder=folder, remote=destination.value, specific=True)
            box.add(toga.Label('Or push this folder beneath a selected remote:'), destination, preview,
                    toga.Button('Push as subfolder…', on_press=specific, style=Pack(height=44)))
        box.add(toga.Button('Cancel', on_press=self.show_locations, style=Pack(height=44)))
        self.show_view(box, destination='files', route='local-push', title='Push local folder')


    def transfer_options(self):
        return load_options(self.private_root / 'transfer-options.json')

    def show_transfer_options(self, widget=None, **kwargs):
        if self.cloud_busy or getattr(self, 'transfer_busy', False) or getattr(self, '_review_starting', False):
            return
        options = self.transfer_options()
        box = toga.Box(style=Pack(direction=COLUMN, margin=12, flex=1))
        rename = toga.Switch('Track renamed files', value=options.track_renames)
        bandwidth = toga.TextInput(value=str(options.bw_limit or ''), placeholder='Unlimited')
        excludes = toga.MultilineTextInput(value='\n'.join(options.excludes), style=Pack(flex=1))
        status = toga.Label('Exclusions apply only to Push; excluded destination files are kept.')
        def save(widget=None, **kw):
            try:
                updated = TransferOptions(track_renames=rename.value,
                    bw_limit=bandwidth.value.strip() or None, excludes=excludes.value.splitlines())
                save_options(self.private_root / 'transfer-options.json', updated)
                self.show_transfers()
            except (OSError, ValueError) as error:
                status.text = str(error)
        box.add(toga.Label('Transfer settings', style=Pack(font_size=22)), rename,
                toga.Label('Bandwidth limit (MB/s)'), bandwidth,
                toga.Label('Push exclusions (one pattern per line)'), excludes, status,
                toga.Button('Save settings', on_press=save, style=Pack(height=44)),
                toga.Button('Cancel', on_press=self.show_transfers, style=Pack(height=44)))
        self.show_view(box, destination='files', route='transfer-settings', title='Transfer settings')

    def begin_transfer_review(self, key=None, *, push=False, remote=None, folder='', storage=None, local_folder=None, specific=False):
        if self.cloud_busy or getattr(self, 'transfer_busy', False) or getattr(self, '_review_starting', False):
            return
        if push and local_folder is not None:
            from features.rclone.transfers.scope import push_scope
            remote, folder = push_scope(local_folder, remote, specific=specific)
        if key is not None:
            job = self.mirror_store().jobs.get(key)
            if job is None:
                return
            remote = job['remote']
            identity = job['identity']
        else:
            identity = None
        self._review_starting = True
        async def run():
            try:
                async with self.remote_activity('Checking connection for transfer'):
                    if not await self.require_remote_credentials_async(remote, identity=identity,
                            resume=lambda: self.begin_transfer_review(key, push=push, remote=remote, folder=folder, storage=storage, local_folder=local_folder, specific=specific)):
                        return False
                return await self.review_transfer(key, push=push, remote=remote, folder=folder, storage=storage, local_folder=local_folder, specific=specific)
            except (OSError, ValueError) as error:
                self.cloud_status.value = 'Review stopped: ' + str(error)[:250]
                return False
            finally:
                self._review_starting = False
        self.transfer_task = self.loop.create_task(run())

    async def review_transfer(self, key, *, push, remote, folder, storage, local_folder=None, specific=False):
        if not await self.mirror_connection_ready():
            return False
        self.transfer_busy = True
        self.set_cloud_busy(True)
        try:
            return await self._review_transfer(key, push=push, remote=remote, folder=folder, storage=storage, local_folder=local_folder, specific=specific)
        finally:
            self.transfer_busy = False
            self.set_cloud_busy(False)
            self.refresh_transfer_status()

    async def _review_transfer(self, key, *, push, remote, folder, storage, local_folder, specific):
        store, client = self.mirror_store(), self.cloud_client
        generation = client.generation
        if key is not None:
            job = dict(store.jobs[key])
        elif push:
            job = await asyncio.to_thread(store.prepare_push, client, local_folder, remote=remote, specific=specific)
        else:
            job = await asyncio.to_thread(store.prepare_review, client, remote, folder, storage=storage)
        key = job['id'] if job['id'] in store.jobs else None
        records = store.original
        signature = self.mirror_job_signature(job)
        def valid():
            return (self.active_host and self.cloud_client is client and client.generation == generation
                    and store.original == records
                    and (key is None or self.mirror_job_signature(store.jobs.get(key)) == signature))
        online = job['remote'] + ':' + folder
        prefix = folder
        if key is not None:
            prefix = job['prefix']
            if job['crypt']:
                prefix = (await asyncio.to_thread(client.request, 'crypt_path', remote=remote, path=prefix,
                    identity=job['cipher_identity'], directory=True, decode=True))['path']
            online = job['remote'] + ':' + prefix
        local = ('LocalCrypt/' if job['crypt'] else 'Local/') + job['target']
        if job['crypt'] and prefix:
            local += '/' + prefix
        saved = self.transfer_options()
        options = TransferOptions(track_renames=saved.track_renames, bw_limit=saved.bw_limit,
            copy_links=not job['crypt'], excludes=saved.excludes if push else ())
        request = ReviewRequest('Push' if push else 'Pull', local if push else online,
            online if push else local, job['identity'], options)
        scanner = native_scanner(client, dict(job, _push=push), store.guard(store.target(job)), options,
                                 cleanup_plan=lambda cancelled: store.cleanup_plan(job, client, cancelled))
        scan = ReviewScan(scanner)
        self.transfer_busy, self.transfer_notification = True, True
        self.set_cloud_busy(True)
        self._transfer_cancel = scan.cancelled
        self.transfer_message = 'Reviewing ' + request.operation + '…'
        self.refresh_transfer_status()
        decision, expected = None, None
        box = toga.Box(style=Pack(direction=COLUMN, margin=12, flex=1))
        paths = toga.Label(f'From: {request.source}\nTo: {request.destination}', style=Pack(margin_bottom=8))
        status = toga.Label('Scanning; comparison does not change files.', style=Pack(margin_bottom=8))
        details = toga.MultilineTextInput(readonly=True, style=Pack(flex=1))
        buttons = toga.Box(style=Pack(direction=ROW))
        async def choose(incomplete):
            nonlocal decision, expected, scan
            if decision is not None or not valid() or (not incomplete and not scan.snapshot().complete):
                return
            confirm.enabled = early.enabled = False
            try:
                accepted = await self.main_window.dialog(toga.ConfirmDialog('Confirm ' + request.operation,
                    request.confirmation(incomplete=incomplete)))
                if not accepted:
                    return
                if not valid():
                    decision = 'cancel'
                    scan.stop()
                elif incomplete:
                    decision = 'proceed'
                    scan.stop()
                else:
                    expected = scan.snapshot()
                    scan = ReviewScan(scanner)
                    self._transfer_cancel = scan.cancelled
                    status.text = 'Checking that the completed review is still current…'
            finally:
                early.enabled = decision is None
        def cancel(widget=None, **kwargs):
            nonlocal decision
            decision = 'cancel'
            scan.stop()
        async def full(widget=None, **kwargs):
            await choose(False)
        async def partial(widget=None, **kwargs):
            await choose(True)
        confirm = toga.Button('Confirm ' + request.operation + '…', on_press=full, enabled=False, style=Pack(flex=1, height=44))
        early = toga.Button('Proceed without full review…', on_press=partial, style=Pack(height=44))
        buttons.add(toga.Button('Cancel', on_press=cancel, style=Pack(height=44)), confirm)
        box.add(toga.Label('Review ' + request.operation, style=Pack(font_size=22)), paths, status, details, early, buttons)
        self._transfer_review_view = box
        self._cancel_transfer_review = cancel
        self.show_view(box, destination='files', route='transfer-review', title='Review ' + request.operation)
        previous = None
        try:
            while True:
                if scan.cancelled.is_set() and decision is None:
                    decision = 'cancel'
                if not valid():
                    cancel()
                    paths.text = 'Connection locked or changed.'
                    details.value = ''
                    if scan.retired.is_set():
                        break
                    await asyncio.sleep(.05)
                    continue
                snapshot = scan.snapshot()
                text = snapshot.text()
                if text != previous:
                    details.value, previous = text, text
                if decision is not None:
                    status.text = 'Stopping comparison…'
                    if scan.retired.is_set():
                        break
                elif expected is not None and scan.retired.is_set():
                    if unchanged(expected, snapshot):
                        decision = 'proceed'
                        break
                    expected = None
                    status.text = 'Files changed or could not be checked. Review the current results and confirm again.'
                elif scan.retired.is_set():
                    confirm.enabled = snapshot.complete and not snapshot.error
                    if snapshot.error:
                        status.text = 'Comparison failed. Retry later, or explicitly proceed without a full review.'
                await asyncio.sleep(.1)
        finally:
            scan.stop()
            while not scan.retired.is_set():
                await asyncio.sleep(.05)
            self._transfer_review_view = None
            self._cancel_transfer_review = None
            paths.text = ''
            details.value = ''
            status.text = 'Review closed.'
            confirm.enabled = early.enabled = False
            self._transfer_cancel = None
            self.transfer_busy = False
            self.set_cloud_busy(False)
            self.refresh_transfer_status()
        if decision != 'proceed' or not valid():
            self.transfer_message = 'Review cancelled. No transfer was started.'
            return False
        work = lambda client, cancel, progress: store.execute_review(job, client, push=push, new=key is None, options=options,
            cancelled=cancel, progress=progress)
        operation = 'push' if push else 'pull'
        return await self.run_mirror_work(work, operation, source=request.source, destination=request.destination)
