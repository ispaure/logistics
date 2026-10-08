"""Encrypt existing comic entries without extraction, conversion or sanitization."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import stat
from tempfile import TemporaryDirectory

from commonUtils.zip_access import open_archive, is_encrypted, validate_members, password_bytes
from commonUtils.streams import stream_signature
from services.zip_passwords import configured_password, remember_verified_password
from .archive_io import archive_unchanged
from .selection import selected_comics


@dataclass
class EncryptionPlan:
    passwords: dict = field(default_factory=dict)
    skipped: list = field(default_factory=list)
    failed: dict = field(default_factory=dict)

    @property
    def missing(self):
        return tuple(path for path, password in self.passwords.items() if not password)


def plan_encryption(targets):
    plan = EncryptionPlan()
    for path in selected_comics(targets):
        try:
            if is_encrypted(path):
                plan.skipped.append(path)
            else:
                plan.passwords[path] = configured_password(path)
        except Exception as error:
            plan.failed[path] = str(error)
    return plan


def encrypt_comic(path, password):
    path = Path(path)
    if not password_bytes(password):
        raise ValueError('A nonempty password is required')
    if path.is_symlink() or path.stat().st_nlink > 1:
        raise ValueError('Encrypt independent regular comic files only')
    snapshot = path.stat()
    if is_encrypted(path):
        return False
    with TemporaryDirectory(prefix='.logistics-comic-', dir=path.parent) as temporary:
        staged = Path(temporary) / 'encrypted.cbz'
        signatures = {}
        with open_archive(path) as source, open_archive(staged, 'w', password=password) as output:
            validate_members(source)
            if not source.infolist():
                raise ValueError('Cannot encrypt an empty comic archive')
            output.comment = source.comment
            for member in source.infolist():
                info = output.zipinfo_cls(member.filename, member.date_time)
                for attr in ('comment', 'external_attr', 'internal_attr', 'create_system'):
                    setattr(info, attr, getattr(member, attr))
                info.compress_type = member.compress_type
                with source.open(member) as incoming, output.open(info, 'w') as outgoing:
                    shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
                with source.open(member) as incoming:
                    signatures[member.filename] = stream_signature(incoming)
        with open_archive(staged, password=password) as result:
            validate_members(result)
            if result.comment != source.comment or [i.filename for i in result.infolist()] != list(signatures):
                raise ValueError('Encrypted archive entries differ from the original')
            for member in result.infolist():
                if not member.flag_bits & 1:
                    raise ValueError('An archive entry was not encrypted')
                with result.open(member) as incoming:
                    if stream_signature(incoming) != signatures[member.filename]:
                        raise ValueError('Encrypted archive contents differ from the original')
        with staged.open('r+b') as handle:
            os.fsync(handle.fileno())
        staged.chmod(stat.S_IMODE(snapshot.st_mode))
        if not archive_unchanged(path, snapshot):
            raise RuntimeError('Comic changed while encrypting; original was not replaced')
        os.replace(staged, path)
    remember_verified_password(path, password)
    return True


def execute_encryption(plan, fallback=None, *, progress=None, cancelled=None):
    """Report completed comics; honor cancellation only between whole archives."""
    result = {'encrypted': [], 'skipped': list(plan.skipped), 'failed': dict(plan.failed),
              'cancelled': False, 'remaining': []}
    items = list(plan.passwords.items())
    total = len(items)
    if progress:
        progress(0, total, None)
    for index, (path, password) in enumerate(items):
        if cancelled and cancelled():
            result['cancelled'] = True
            result['remaining'] = [path for path, _ in items[index:]]
            break
        if progress:
            progress(index, total, path)
        try:
            if encrypt_comic(path, password or fallback):
                result['encrypted'].append(path)
            else:
                result['skipped'].append(path)
        except Exception as error:
            result['failed'][path] = str(error)
        if progress:
            progress(index + 1, total, None)
    return result
