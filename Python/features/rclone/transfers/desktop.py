"""Desktop transfer planning; toolkit presentation stays in workflow.py."""
from configparser import ConfigParser
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping
from uuid import uuid4

from commonUtils.runtime.operations import check_cancelled
from features.rclone import session
from . import sync
from .review import ReviewRequest
from .review_cli import scanner
from .service import TransferPlan
from .transfer_options import TransferOptions


@dataclass(frozen=True)
class DesktopTransferRequest:
    source: str
    destination: str
    operation: str
    config: Path
    binary: Path
    options: TransferOptions = TransferOptions()
    crypt_item: object | None = None
    before_start: Callable = field(default=lambda: None, repr=False)
    launch: Mapping = field(default_factory=dict, repr=False)

    def __post_init__(self):
        allowed = {'query', 'wait_for_output', 'dry_run', 'integrated'}
        if set(self.launch) - allowed or any(type(value) is not bool for value in self.launch.values()):
            raise ValueError('Use explicit boolean desktop transfer launch options.')
        object.__setattr__(self, 'source', str(self.source))
        object.__setattr__(self, 'destination', str(self.destination))
        object.__setattr__(self, 'config', Path(self.config))
        object.__setattr__(self, 'binary', Path(self.binary))
        object.__setattr__(self, 'launch', MappingProxyType(dict(self.launch)))


def _snapshot_config(path):
    """Saved credentials use a private child so rclone cannot rewrite the file.

    This also keeps OAuth refreshes during comparison/execution from invalidating
    the original file binding. Session-backed requests already have that boundary.
    """
    if path.suffix == '.session':
        return path, lambda: None
    parser = ConfigParser(interpolation=None)
    with path.open(encoding='utf-8') as stream:
        parser.read_file(stream)
    values = {name: dict(parser[name]) for name in parser.sections()}
    context = path.with_name('transfer-' + uuid4().hex + '.session')
    session.remember(context, values, private=True)
    return context, lambda: session.forget(context)


def _compare(transfer, config_path, emit, cancelled):
    from features.rclone.localcrypt.backend import CryptResources
    binary, item = transfer.binary, transfer.crypt_item
    provider = CryptResources(item, binary=binary) if item is not None and item.data.exists() else None
    decoded = {}
    directory_probe = '.logistics-review-directory'
    encoded_probe = None
    def decode(value, cancelled, *, reverse=False):
        flags = ['--reverse'] if reverse else []
        if provider is not None:
            result = provider.command('cryptdecode', '', *flags, value, cancelled=cancelled).decode('utf-8')
        else:
            from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
            environment, remote, _ = session.launch(config_path, item.remote + ':', '')
            result = run_bytes([str(binary), '--config', session.NULL_CONFIG, 'cryptdecode', *flags, remote, value],
                environment=environment, max_output=65536, cancelled=cancelled).decode('utf-8')
        plain = result.partition('\t')[2].removeprefix(' ').removesuffix('\n')
        return None if plain == 'Failed to decrypt' or not plain else plain
    def display(path, cancelled, *, directory=False):
        nonlocal encoded_probe
        if item is None:
            return path
        key = (path, directory)
        if key not in decoded:
            value = path
            if directory:
                # cryptdecode decodes files. A synthetic final file component
                # lets the cipher apply directory rules to every real component,
                # including filename_encryption=off and unencrypted directories.
                # This is a name-only operation; no probe is created on disk.
                if encoded_probe is None:
                    encoded_probe = decode(directory_probe, cancelled, reverse=True)
                if encoded_probe is None:
                    raise ValueError('Could not resolve encrypted directory names.')
                value = path + '/' + encoded_probe
            plain = decode(value, cancelled)
            if directory and plain is not None:
                suffix = '/' + directory_probe
                if not plain.endswith(suffix):
                    raise ValueError('Invalid encrypted directory review name.')
                plain = plain[:-len(suffix)]
            decoded[key] = path if plain is None else plain
        return decoded[key]
    def cleanup_plan(cancelled):
        if item is None or transfer.operation != 'Push':
            return {}
        from features.rclone.transfers.local_policy import cleanup_candidates
        return cleanup_candidates(item.data, display, cancelled)
    try:
        return scanner(binary, transfer.source, transfer.destination, config_path, transfer.options,
            display_path=display,
            display_directory=lambda path, cancelled: display(path, cancelled, directory=True),
            cleanup_plan=cleanup_plan)(emit, cancelled)
    finally:
        if provider is not None:
            provider.close()


def build_plan(transfer, credentials):
    if not isinstance(transfer, DesktopTransferRequest):
        raise TypeError('Choose a desktop transfer request.')
    from features.rclone.localcrypt.mapping import for_path
    item = transfer.crypt_item or for_path(transfer.source if transfer.operation == 'Push' else transfer.destination)
    transfer = replace(transfer, crypt_item=item,
        options=replace(transfer.options, copy_links=False) if item is not None else transfer.options)
    request = ReviewRequest(transfer.operation, transfer.source, transfer.destination,
                            str(transfer.config), transfer.options)
    path = transfer.config
    grant = credentials.capture(path)
    def active():
        try:
            grant.check()
            return True
        except (OSError, ValueError):
            return False
    def compare(emit, cancelled):
        stopping = lambda: cancelled() or not active()
        check_cancelled(stopping)
        config, release = _snapshot_config(path)
        try:
            check_cancelled(stopping)
            return _compare(transfer, config, emit, stopping)
        finally:
            release()
    def execute(approved, context):
        check_cancelled(context.cancelled)
        transfer.before_start()
        # Publishing a copy association may call arbitrary host hooks. Never
        # let that gap bind the approved transfer to replacement credentials.
        check_cancelled(context.cancelled)
        config, release = _snapshot_config(path)
        retained = False
        def launched(window):
            nonlocal retained
            window.runner.completed.connect(lambda *_: release())
            window.destroyed.connect(lambda *_: release())
            retained = True
            if not window.busy:
                release()
        try:
            check_cancelled(context.cancelled)
            return sync.rclone_sync(approved.source, approved.destination, config_path=config,
                executable_path=transfer.binary, track_renames=approved.options.track_renames,
                bw_limit=approved.options.bw_limit, copy_links=approved.options.copy_links,
                excludes=approved.options.excludes, cancelled=context.cancelled,
                on_launch=launched, **transfer.launch)
        finally:
            if not retained:
                release()
    return TransferPlan(request, compare, active, execute, active=active)
