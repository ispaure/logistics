"""Native load requests; the bridge remains the atomic publication authority."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from io import BytesIO

from features.rclone.credential_loading import CredentialStage, CredentialResult
from .cloud import PACKAGE_LIMIT, download_name


@dataclass(frozen=True)
class NativeCredentialLoad:
    access: object = field(repr=False)
    reference: object = field(repr=False)
    remember: bool = True


@dataclass(frozen=True)
class NativeSMBLoad:
    name: str
    host: str
    user: str
    domain: str = ''
    port: str = '445'
    remember: bool = True


class _Package:
    def __init__(self, access, reference):
        with access.open(reference) as (name, stream):
            self.data = stream.read(PACKAGE_LIMIT + 1)
        if len(self.data) > PACKAGE_LIMIT:
            raise ValueError('Credential ZIPs are limited to 1 MiB.')
        self.name = download_name(name)
        self._aliases = dict(access.aliases(reference)) if hasattr(access, 'aliases') else {}

    @contextmanager
    def open(self, reference=None):
        with BytesIO(self.data) as stream:
            yield self.name, stream

    def aliases(self, reference=None):
        return dict(self._aliases)


def prepare(client, request, password):
    if not isinstance(request, (NativeCredentialLoad, NativeSMBLoad)):
        raise TypeError('Choose a native credential package or SMB connection.')
    if type(request.remember) is not bool:
        raise ValueError('Choose saved or session-only credentials.')
    generation = client.generation
    secret = [password]
    try:
        package = _Package(request.access, request.reference) if isinstance(request, NativeCredentialLoad) else None
    except BaseException:
        secret.clear()
        raise
    def publish(context):
        if package is not None:
            names = client.import_package(package, None, secret[0], remember=request.remember)
        else:
            names = client.add_smb(request.name, request.host, request.user, secret[0],
                                   request.domain, request.port, remember=request.remember)
        return CredentialResult(client.package_name, tuple(names), request.remember, client.generation)
    def close():
        secret.clear()
        if package is not None:
            package.data = b''
            package._aliases.clear()
    return CredentialStage(publish, lambda: client.generation == generation, close)


async def run_credentials(operation, *args, valid=lambda: True):
    """Keep publication ownership until a cancelled native worker retires."""
    import asyncio
    from threading import Event
    from features.rclone.credential_loading import CredentialContext
    cancelled = Event()
    task = asyncio.create_task(asyncio.to_thread(operation, *args,
        context=CredentialContext(cancelled.is_set, valid)))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        cancelled.set()
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        try:
            task.result()
        except BaseException:
            pass
        raise
