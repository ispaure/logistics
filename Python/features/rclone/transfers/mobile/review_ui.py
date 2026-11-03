"""Native presentation over the same review state and decisions as desktop."""
import asyncio
from typing import Protocol

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from features.rclone.transfers.transfer_options import TransferOptions, load_options, save_options
from features.rclone.transfers.service import TransferContext
from .plan import NativeTransferRequest
from features.rclone.mobile.messages import import_hint


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
    return snapshot, snapshot.complete and session.can_approve()


class ReviewPresentation(Protocol):
    app: object
    async def confirm(self, request, *, incomplete: bool) -> bool: ...
    def scanning(self, session) -> None: ...
    def show(self, box, cancel, request) -> None: ...
    def close(self) -> None: ...
    def retained(self) -> bool: ...


class TransferReviewDialog:
    """One private surface over the shared review/approval lifetime."""
    def __init__(self, view: ReviewPresentation):
        self.view = view
        self.surface = None

    async def run(self, session):
        try:
            return await self._present(session)
        finally:
            if self.surface is not None:
                self.surface.dispose()
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
        from features.rclone.transfers.presentation import ReviewProjection
        from .surface import TransferSurface
        projection = ReviewProjection(session.request)
        closed = confirming = False
        rendered = None
        def publish():
            if closed or self.surface.closed or rendered is None:
                return
            self.view.review_snapshot = rendered
            self.surface.review_ready = rendered.complete and session.can_approve() and not confirming
            self.surface.update(projection.model(rendered, state=session.state,
                can_confirm=self.surface.review_ready,
                can_early=not confirming and session.can_approve(incomplete=True)))

        async def choose(incomplete=False):
            nonlocal confirming
            if (closed or confirming or rendered is None or not incomplete and not rendered.complete
                    or not session.can_approve(incomplete=incomplete)):
                return
            confirming = True
            publish()
            try:
                accepted = await self.view.confirm(session.request, incomplete=incomplete)
                if not closed and accepted and session.approve(incomplete=incomplete):
                    self.view.scanning(session)
            finally:
                confirming = False
                publish()

        def cancel(widget=None, **kwargs):
            session.cancel()

        async def command(action, args):
            if action == 'approve':
                await choose(False)
            elif action == 'early':
                await choose(True)
            elif action == 'filter':
                projection.select(kind=args.get('kind'), query=args.get('query', ''))
                publish()
            elif action in ('next', 'previous'):
                projection.select(step=1 if action == 'next' else -1)
                publish()
            elif action == 'background':
                cancel()

        surface = self.surface = TransferSurface(self.view.app, command)
        surface.approve_review, surface.cancel_review = choose, cancel
        surface.review_ready = False
        try:
            self.view.show(surface, cancel, session.request)
            while True:
                if not self.view.retained():
                    session.cancel()
                state = session.poll()
                if not session.valid():
                    surface.dispose()
                else:
                    rendered, _ = _display_review(session)
                    publish()
                if state in ('approved', 'cancelled'):
                    break
                await asyncio.sleep(.1)
        finally:
            closed = True
            surface.review_ready = False
            projection.clear()
            surface.dispose()
        return session.approved


class MobileReviewPresentation:
    def __init__(self, owner):
        self.owner = owner
        self.app = owner.app
        self.review_snapshot = None

    async def confirm(self, request, *, incomplete):
        counts = self.review_snapshot.counts
        message = (f'{counts["add"]:,} added · {counts["replace"]:,} replaced · {counts["delete"]:,} deleted.\n'
                   + (f'{counts["cleanup"]:,} local generated entries removed before Push.\n' if counts['cleanup'] else '')
                   + f'Source: {request.source}\nDestination: {request.destination}\n\n'
                   + ('Comparison incomplete. Additional replacements and deletions may occur.\n' if incomplete else '')
                   + 'Destination replacements and deletions have no backup or undo.')
        return await self.owner.main_window.dialog(toga.ConfirmDialog(
            request.operation + ' these changes?', message))

    def scanning(self, session):
        self.owner._transfer_cancel = session.scan.cancelled

    def show(self, box, cancel, request):
        self.owner._transfer_review_view = box
        self.owner._cancel_transfer_review = cancel
        self.owner.show_view(box, destination='files', route='transfer-review', title='Review changes')

    def retained(self):
        return any(screen[0] == 'transfer-review' for screen in self.owner.routes.screens['files'])

    def close(self):
        owner = self.owner
        self.review_snapshot = None
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
        from .surface import TransferSurface
        remotes = sorted(self.loaded_remote_names(), key=str.casefold)
        selection = dict(specific=False, remote=remotes[0] if remotes else None)
        previous = getattr(self, '_transfer_setup_surface', None)
        if previous is not None:
            previous.dispose()
        async def command(action, args):
            if action == 'scope':
                selection['specific'] = args.get('specific') == '1'
                selection['remote'] = args.get('remote') if args.get('remote') in remotes else None
                target = (selection['remote'] or '') + ':' + folder if selection['specific'] else folder + ':'
                surface.update(dict(surface.model, destination=target))
            elif action == 'start-review':
                if selection['specific'] and selection['remote'] is None:
                    return
                self.begin_transfer_review(push=True, local_folder=folder,
                    remote=selection['remote'] if selection['specific'] else None, specific=selection['specific'])
            elif action == 'settings':
                self.show_transfer_options()
            elif action == 'background':
                surface.dispose()
                self.routes.back()
        surface = self._transfer_setup_surface = TransferSurface(self.app, command)
        surface.update(dict(mode='setup', operation='Push', workspace=folder, source='Local/' + folder,
                            destination=folder + ':', remotes=remotes))
        self.show_view(surface, destination='files', route='local-push', title='Transfer')


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
                self.routes.back()
            except (OSError, ValueError) as error:
                status.text = str(error)
        box.add(toga.Label('Transfer settings', style=Pack(font_size=22)), rename,
                toga.Label('Bandwidth limit (MB/s)'), bandwidth,
                toga.Label('Push exclusions (one pattern per line)'), excludes, status,
                toga.Button('Save settings', on_press=save, style=Pack(height=44)),
                toga.Button('Cancel', on_press=lambda widget, **kw: self.routes.back(), style=Pack(height=44)))
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
                setup = getattr(self, '_transfer_setup_surface', None)
                if setup is not None and not setup.closed:
                    setup.update(dict(setup.model, notice=self.cloud_status.value))
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
