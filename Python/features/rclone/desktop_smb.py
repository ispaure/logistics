"""Desktop Home Server records and guarded SMB credential admission."""
from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
from ipaddress import ip_address
import json
from pathlib import Path
import re
from typing import Callable
from uuid import uuid4
from zipfile import BadZipFile

from commonUtils.archives.zip_access import open_archive
from commonUtils.filesystem.links import is_junction
from commonUtils.integrations.wrappers.cmdShellWrapper.binary import BinaryCommandError, run_bytes
from commonUtils.persistence import atomic_write_bytes
from commonUtils.runtime.operations import check_cancelled
from . import session
from .credential_loading import CredentialResult, CredentialStage
from .storage import application_root

CONTEXT_NAME = 'Network shares.session'
RECORD_LIMIT = 32 * 1024


def _root():
    return application_root() / 'Connections' / 'Servers'


def _name(value):
    if not re.fullmatch(r'[\w][\w .+-]{0,79}', value) or len(value.encode()) > 80:
        raise ValueError('Use a short connection name with letters, numbers, spaces or . _ + - characters.')
    return value


@dataclass(frozen=True)
class ServerRecord:
    name: str
    context: Path
    encrypted: bytes = field(default=b'', repr=False)

    @classmethod
    def new(cls, name):
        name = _name(name)
        identity = sha256(name.casefold().encode()).hexdigest()
        return cls(name, _root() / identity / CONTEXT_NAME)

    @property
    def path(self):
        return self.context.with_name('connection.json')

    @property
    def connected(self):
        return session.names(self.context) is not None


def is_server_context(context):
    path = Path(context)
    return path.name == CONTEXT_NAME and path.parent.parent == _root()


def _check_storage(path):
    for directory in (_root().parent, _root(), path.parent, path):
        if directory.is_symlink() or is_junction(directory):
            raise ValueError('Linked server connection storage is unavailable.')


def _read(path):
    _check_storage(path)
    try:
        with path.open('rb') as stream:
            raw = stream.read(RECORD_LIMIT + 1)
    except FileNotFoundError:
        return None
    if len(raw) > RECORD_LIMIT:
        raise ValueError('Server connection record exceeds its size limit.')
    try:
        value = json.loads(raw)
        record = ServerRecord.new(value['name'])
        if value['schema'] != 1 or path != record.path:
            raise ValueError
        return ServerRecord(record.name, record.context, b64decode(value['encrypted'], validate=True))
    except (ValueError, KeyError, TypeError):
        raise ValueError('Server connection record is invalid.') from None


def records():
    root = _root()
    if any(path.is_symlink() or is_junction(path) for path in (root.parent, root)):
        return []
    found = []
    for path in root.glob('*/connection.json'):
        try:
            record = _read(path)
        except (OSError, ValueError):
            continue
        if record is not None:
            found.append(record)
    return sorted(found, key=lambda item: item.name.casefold())


def record_for(context):
    if not is_server_context(context):
        return None
    try:
        return _read(Path(context).with_name('connection.json'))
    except (OSError, ValueError):
        return None


@dataclass(frozen=True)
class SMBEndpoint:
    host: str
    user: str
    domain: str = 'WORKGROUP'
    port: str = '445'

    def settings(self):
        host = self.host
        bracketed = host.startswith('[') and host.endswith(']')
        try:
            address = ip_address(host[1:-1] if bracketed else host)
            valid_host = '%' not in host and (not bracketed or address.version == 6)
            host = f'[{address}]' if address.version == 6 else str(address)
        except ValueError:
            valid_host = re.fullmatch(r'[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*\.?', host)
        if not valid_host or len(self.host) > 253:
            raise ValueError('Enter a server hostname or IP address without a URL or share path.')
        if not self.user or len(self.user.encode()) > 256:
            raise ValueError('Enter an SMB username or choose guest access.')
        if any(len(value.encode()) > 8192 or any(c in value for c in '\0\r\n')
               for value in (self.user, self.domain)):
            raise ValueError('Enter a valid SMB username and domain.')
        port = self.port or '445'
        if not re.fullmatch(r'[0-9]{1,5}', port) or not 1 <= int(port) <= 65535:
            raise ValueError('SMB port must be between 1 and 65535.')
        return dict(type='smb', host=host, user=self.user, domain=self.domain, port=str(int(port)),
                    use_kerberos='false')


@dataclass(frozen=True)
class DesktopSMBLoad:
    record: ServerRecord
    binary: Path
    endpoint: SMBEndpoint | None
    remember: bool = False
    adding: bool = False
    cancelled: Callable[[], bool] = field(default=lambda: False, repr=False)


@dataclass(frozen=True)
class SMBSecrets:
    password: str = field(default='', repr=False)
    passphrase: str = field(default='', repr=False)


def _encode(settings, passphrase):
    buffer = BytesIO()
    with open_archive(buffer, 'w', password=passphrase) as archive:
        archive.writestr('server.json', json.dumps(settings, ensure_ascii=False))
    return buffer.getvalue()


def _decode(encrypted, passphrase):
    try:
        with open_archive(BytesIO(encrypted), password=passphrase) as archive:
            entry, = archive.infolist()
            if (entry.filename != 'server.json' or entry.file_size > RECORD_LIMIT
                    or getattr(entry, 'wz_aes_strength', None) != 3):
                raise ValueError
            values = json.loads(archive.read(entry))
        settings = SMBEndpoint(values['host'], values['user'], values['domain'], values['port']).settings()
        password = values['pass']
        if not isinstance(password, str) or not re.fullmatch(r'[A-Za-z0-9_-]{22,5500}', password):
            raise ValueError
        return dict(settings, **{'pass': password})
    except (BadZipFile, OSError, RuntimeError, TypeError, ValueError, KeyError, EOFError):
        raise ValueError('Could not unlock the saved server credentials. Check the passphrase.') from None


def _obscure(binary, password, cancelled):
    secret = password.encode()
    if len(secret) > 4096 or any(c in secret for c in (b'\0', b'\r', b'\n')):
        raise ValueError('Enter an SMB password without line breaks or NUL characters.')
    try:
        hidden = run_bytes([str(binary), '--config', session.NULL_CONFIG, 'obscure', '-'],
                           input_data=secret + b'\n', max_output=8192, cancelled=cancelled).strip()
    except BinaryCommandError:
        raise ValueError('Could not prepare the SMB password.') from None
    if not re.fullmatch(rb'[A-Za-z0-9_-]{22,5500}', hidden):
        raise ValueError('Could not prepare the SMB password.')
    return hidden.decode('ascii')


def prepare(request, secrets):
    """Probe using a private child, then publish only after successful authentication."""
    from .remote_resources import RemoteResources

    record, cancelled = request.record, request.cancelled
    prior = _read(record.path)
    if request.adding:
        if prior is not None:
            raise ValueError('A connection with that name already exists. Choose another name.')
    elif prior != record or record.connected:
        raise ValueError('This server connection changed. Refresh Workspaces and try again.')

    encrypted = record.encrypted
    if encrypted:
        settings = _decode(encrypted, secrets.passphrase)
    else:
        settings = request.endpoint.settings()
        settings['pass'] = _obscure(request.binary, secrets.password, cancelled)
        if request.remember:
            passphrase = secrets.passphrase
            if not 12 <= len(passphrase) <= 1024:
                raise ValueError('Choose a credential passphrase of 12 to 1024 characters.')
            encrypted = _encode(settings, passphrase)

    probe = record.context.with_name(f'probe-{uuid4().hex}.session')
    try:
        session.remember(probe, {record.name: settings}, private=True)
        provider = RemoteResources(probe, record.name, binary=request.binary)
        try:
            provider.list(cancelled=cancelled)
        finally:
            provider.close()
    except BaseException:
        settings.clear()
        raise
    finally:
        session.forget(probe)

    def valid():
        return _read(record.path) == prior and not record.connected

    def publish(context):
        if request.adding:
            def validate():
                check_cancelled(context.cancelled)
                _check_storage(record.path)
                if not context.valid() or not valid():
                    raise ValueError('This server connection changed. Try again.')
            _check_storage(record.path)
            record.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            payload = json.dumps(dict(schema=1, name=record.name, encrypted=b64encode(encrypted).decode()))
            atomic_write_bytes(record.path, payload.encode(), overwrite=False, file_mode=0o600, validate=validate)
        proof = {'state_password': secrets.passphrase, 'state_identity': sha256(encrypted).hexdigest()} if encrypted else {}
        session.remember(record.context, {record.name: settings}, **proof)
        return CredentialResult(record.context, (record.name,), bool(encrypted))

    return CredentialStage(publish, valid, settings.clear)


def forget(record):
    from .desktop_service import service

    service.credentials.lock(record.context)
    _check_storage(record.path)
    record.path.unlink(missing_ok=True)
