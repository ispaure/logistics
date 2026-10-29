"""Native presentation over the same review state and decisions as desktop."""
import asyncio
from typing import Protocol

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from features.rclone.transfers.transfer_options import TransferOptions, load_options, save_options
from features.rclone.transfers.service import TransferContext
from .plan import NativeTransferRequest


async def _prepare(transfers, transfer):
    task = asyncio.create_task(asyncio.to_thread(transfers.review, transfer))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Keep the host busy until late preparation and comparison retire. A
        # late native cancellation must not interrupt the next transfer instead.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        try:
            review = task.result().review
        except BaseException:
            pass
        else:
            review.cancel()
            while not review.scan.retired.is_set():
                try:
                    await asyncio.sleep(.05)
                except asyncio.CancelledError:
                    continue
        raise


def _display_review(session):
    snapshot = session.scan.snapshot()
    # A worker can finish between snapshot() and can_approve(). Never enable
    # full approval while the rendered comparison is still visibly partial.
    return snapshot.text(), snapshot.complete and session.can_approve()


class ReviewPresentation(Protocol):
    async def confirm(self, request, *, incomplete: bool) -> bool: ...
    def scanning(self, session) -> None: ...
    def show(self, box, cancel, request) -> None: ...
    def close(self) -> None: ...


class TransferReviewDialog:
    """Render and retire one review; execution stays in the transfer workflow."""

    def __init__(self, view: ReviewPresentation):
        self.view = view

    async def run(self, session):
        try:
            return await self._present(session)
        finally:
            session.scan.stop()
            try:
                while not session.scan.retired.is_set():
                    try:
                        await asyncio.sleep(.05)
                    except asyncio.CancelledError:
                        continue
            finally:
                self.view.close()

    async def _present(self, session):
        request = session.request
        box = toga.Box(style=Pack(direction=COLUMN, margin=12, flex=1))
        paths = toga.Label(f'From: {request.source}\nTo: {request.destination}', style=Pack(margin_bottom=8))
        status = toga.Label('Scanning; comparison does not change files.', style=Pack(margin_bottom=8))
        details = toga.MultilineTextInput(readonly=True, style=Pack(flex=1))
        buttons = toga.Box(style=Pack(direction=ROW))
        closed = False
        confirming = False
        async def choose(incomplete):
            nonlocal confirming
            if closed or confirming or not session.can_approve(incomplete=incomplete):
                return
            confirming = True
            confirm.enabled = early.enabled = False
            try:
                accepted = await self.view.confirm(request, incomplete=incomplete)
                if not closed and accepted and session.approve(incomplete=incomplete):
                    self.view.scanning(session)
            finally:
                confirming = False
                if not closed:
                    early.enabled = session.can_approve(incomplete=True)
        def cancel(widget=None, **kwargs):
            session.cancel()
        async def full(widget=None, **kwargs):
            await choose(False)
        async def partial(widget=None, **kwargs):
            await choose(True)
        confirm = toga.Button('Confirm ' + request.operation + '…', on_press=full, enabled=False, style=Pack(flex=1, height=44))
        early = toga.Button('Proceed without full review…', on_press=partial, style=Pack(height=44))
        buttons.add(toga.Button('Cancel', on_press=cancel, style=Pack(height=44)), confirm)
        box.add(toga.Label('Review ' + request.operation, style=Pack(font_size=22)), paths, status, details, early, buttons)
        previous = None
        try:
            self.view.show(box, cancel, request)
            while True:
                state = session.poll()
                full_ready = False
                if not session.valid():
                    paths.text = 'Connection locked or changed.'
                    details.value = ''
                else:
                    text, full_ready = _display_review(session)
                    if text != previous:
                        details.value, previous = text, text
                confirm.enabled = full_ready and not confirming
                early.enabled = not confirming and session.can_approve(incomplete=True)
                notices = dict(stopping='Stopping comparison…', checking='Checking that the completed review is still current…',
                    changed='Files changed or could not be checked. Review the current results and confirm again.',
                    failed='Comparison failed. Retry later, or explicitly proceed without a full review.')
                if state in notices:
                    status.text = notices[state]
                if state in ('approved', 'cancelled'):
                    break
                await asyncio.sleep(.1)
        finally:
            closed = True
            paths.text = ''
            details.value = ''
            status.text = 'Review closed.'
            confirm.enabled = early.enabled = False
        return session.approved


class MobileReviewPresentation:
    """Own the controller fields and navigation effects of a review dialog."""

    def __init__(self, owner):
        self.owner = owner

    async def confirm(self, request, *, incomplete):
        return await self.owner.main_window.dialog(toga.ConfirmDialog(
            'Confirm ' + request.operation, request.confirmation(incomplete=incomplete)))

    def scanning(self, session):
        self.owner._transfer_cancel = session.scan.cancelled

    def show(self, box, cancel, request):
        self.owner._transfer_review_view = box
        self.owner._cancel_transfer_review = cancel
        self.owner.show_view(box, destination='files', route='transfer-review',
                             title='Review ' + request.operation)

    def close(self):
        owner = self.owner
        owner._transfer_review_view = None
        owner._cancel_transfer_review = None
        try:
            screens = owner.routes.screens['files']
            index = next((index for index, screen in enumerate(screens)
                          if screen[0] == 'transfer-review'), None)
            if index is not None:
                owner.routes.trim('files', index)
                owner.routes.render('files')
        finally:
            owner._transfer_cancel = None
            owner.transfer_busy = False
            owner.set_cloud_busy(False)
            owner.refresh_transfer_status()


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
        self.show_view(box, route='transfer-settings', title='Transfer settings')

    def begin_transfer_review(self, key=None, *, push=False, remote=None, folder='', storage=None, local_folder=None, specific=False):
        if self.cloud_busy or getattr(self, 'transfer_busy', False) or getattr(self, '_review_starting', False):
            return
        # Workspaces can start a mapped transfer before any remote browser has
        # created the status/progress controls used by credential checks.
        self.show_cloud(present=False)
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
        saved = self.transfer_options()
        options = TransferOptions(track_renames=saved.track_renames, bw_limit=saved.bw_limit,
            copy_links=not job['crypt'], excludes=saved.excludes if push else ())
        from features.rclone.mobile.service import native_service
        transfers = native_service(client).transfers
        transfer = NativeTransferRequest(store=store, job=job, push=push, new=key is None,
            options=options, generation=generation,
            host_active=lambda: self.active_host and self.cloud_client is client)
        prepared = await _prepare(transfers, transfer)
        request = prepared.request
        session = prepared.review
        self.transfer_busy, self.transfer_notification = True, True
        self.set_cloud_busy(True)
        self._transfer_cancel = session.scan.cancelled
        self.transfer_message = 'Reviewing ' + request.operation + '…'
        self.refresh_transfer_status()
        dialog = TransferReviewDialog(MobileReviewPresentation(self))
        await dialog.run(session)
        if not session.approved:
            self.transfer_message = 'Review cancelled. No transfer was started.'
            return False
        def work(client, cancel, progress):
            return transfers.execute(prepared, TransferContext(cancel, progress))
        operation = 'push' if push else 'pull'
        return await self.run_mirror_work(work, operation, source=request.source, destination=request.destination)
