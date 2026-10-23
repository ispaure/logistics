"""Captured native transfer plans and comparison transport, without widgets."""
from dataclasses import dataclass, field
from hashlib import sha256
import json
from threading import Event, Thread
from types import MappingProxyType
from typing import Callable, Mapping
from uuid import uuid4

from commonUtils.runtime.operations import check_cancelled
from features.rclone.transfers.review import ReviewRequest, replace_changes
from features.rclone.transfers.service import TransferPlan
from features.rclone.transfers.transfer_options import TransferOptions


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
            check_cancelled(cancelled)
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


@dataclass(frozen=True)
class NativeTransferRequest:
    store: object
    job: Mapping
    push: bool
    new: bool
    options: TransferOptions
    generation: int
    host_active: Callable[[], bool] = field(default=lambda: True, repr=False)

    def __post_init__(self):
        if type(self.push) is not bool or type(self.new) is not bool:
            raise ValueError('Transfer direction and mapping status must be explicit.')
        object.__setattr__(self, 'job', MappingProxyType(dict(self.job)))


def build_plan(client, transfer, credentials):
    if not isinstance(transfer, NativeTransferRequest):
        raise TypeError('Choose a native transfer request.')
    if client.generation != transfer.generation:
        raise ValueError('Credentials changed. Review the transfer again.')
    store, job = transfer.store, dict(transfer.job)
    store.validate(job)
    store.check_records()
    records = store.original
    signature = store.signature(job)
    grant = credentials.capture(job['remote'])
    target = store.guard(store.target(job))
    def active():
        try:
            return (not grant.revoked() and client.generation == transfer.generation
                    and transfer.host_active() and store.guard(store.target(job)) == target)
        except (OSError, ValueError):
            return False
    def valid():
        current = store.jobs.get(job['id'])
        try:
            return (active() and store.original == records
                    and (store.signature(current) == signature if current is not None else transfer.new))
        except (KeyError, TypeError):
            return False
    check_cancelled(lambda: not active())
    prefix = job['prefix']
    if job['crypt']:
        prefix = client.request('crypt_path', remote=job['remote'], path=prefix,
            identity=job['cipher_identity'], directory=True, decode=True)['path']
    online = job['remote'] + ':' + prefix
    local = ('LocalCrypt/' if job['crypt'] else 'Local/') + job['target']
    if job['crypt'] and prefix:
        local += '/' + prefix
    request = ReviewRequest('Push' if transfer.push else 'Pull', local if transfer.push else online,
                            online if transfer.push else local, job['identity'], transfer.options)
    scan = native_scanner(client, dict(job, _push=transfer.push), target,
        transfer.options, cleanup_plan=lambda cancelled: store.cleanup_plan(dict(job), client, cancelled))
    def compare(emit, cancelled):
        stopping = lambda: cancelled() or not active()
        check_cancelled(stopping)
        return scan(emit, stopping)
    def execute(approved, context):
        return store.execute_review(dict(job), client, push=transfer.push, new=transfer.new,
            options=approved.options, cancelled=context.cancelled, progress=context.progress)
    return TransferPlan(request, compare, valid, execute, active=active)
