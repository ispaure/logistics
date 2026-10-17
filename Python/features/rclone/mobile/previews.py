"""Encrypted mobile preview I/O; presentation stays with the provider host."""
import base64
from pathlib import Path

from commonUtils.runtime.operations import check_cancelled
from features.rclone.localcrypt.mobile.archive_source import NativeSource


def preview_source(provider, client, row, *, password='', cancelled=lambda: False):
    check_cancelled(cancelled)
    path = provider._guard(provider._locate(row['path']))
    return NativeSource(client, provider.record(row['path']), path,
                        password=password, cancelled=cancelled)


def encrypted_thumbnail(provider, client, row, size, *, password='', cancelled=lambda: False):
    check_cancelled(cancelled)
    item = preview_source(provider, client, row, password=password, cancelled=cancelled)
    suffix = Path(row['path']).suffix.lower()
    member = ''
    if suffix in {'.zip', '.cbz', '.epub'}:
        from services.documents.readers import PrivateReader
        reader = PrivateReader(item.name, source=item)
        member = reader.book.cover_path() if reader.book else reader.pages[0]
        if not member:
            return b''
    elif suffix not in {'.png', '.jpg', '.jpeg', '.webp'}:
        return b''
    data = item.request('crypt_thumbnail', member=member, width=size[0], height=size[1])
    check_cancelled(cancelled)
    return base64.b64decode(data['data'], validate=True)
