"""Version-bound sources for the desktop selected-file transfer worker."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import json
from pathlib import Path
import re
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from features.rclone.storage import application_root
from features.rclone import session
from services.documents.credential_state import DesktopCredentialCipher, credential_authority
from .download_recovery import DownloadQueue, RestartRequired


def desktop_queue(provider):
    provider.check()
    authority = [str(provider.config_path), provider.remote, credential_authority(provider)]
    if provider.session_only:
        cipher = DesktopCredentialCipher(provider)
        try:
            authority.append(cipher.identity)
        except PermissionError:
            raise RestartRequired('This session has no password-bound transfer record. Download from byte zero?') from None
    else:
        from services.documents.video_state import DesktopCipher
        saved = DesktopCipher(SimpleNamespace(provider=provider))
        class SavedCipher:
            def transform(self, data, decode=False):
                return saved.transform(data, 'Logistics download queue v1', decode)
        cipher = SavedCipher()
    return DownloadQueue(application_root(), authority, provider.check, cipher)


class HttpRanges:
    """Require a strong entity tag, conditional GET and the exact requested interval."""
    def __init__(self, url, check):
        self.url, self.check = url, check

    def request(self, method, headers):
        self.check()
        request = Request(self.url, headers={'Accept-Encoding': 'identity', **headers}, method=method)
        try:
            return urlopen(request, timeout=30)
        except HTTPError as error:
            error.close()
            if method == 'HEAD' and error.code in (405, 501):
                raise RestartRequired('The server cannot verify the source version. Download from byte zero?') from None
            if error.code in (412, 416):
                raise ValueError('The server file changed. Inspect the interrupted download.') from None
            raise OSError(f'The download server returned HTTP {error.code}.') from None

    def stat(self):
        with self.request('HEAD', {}) as reply:
            tag = reply.headers.get('ETag', '')
            length = reply.headers.get('Content-Length', '')
            if (not re.fullmatch(r'"[^"\s]*"', tag) or not length.isdecimal()
                    or reply.headers.get('Accept-Ranges', '').lower() != 'bytes'
                    or reply.headers.get('Content-Encoding', 'identity') != 'identity'):
                raise RestartRequired('The server did not confirm a stable version and byte ranges. Download from byte zero?')
            return dict(size=int(length), version=[reply.geturl(), tag], encoded=False)

    def read(self, version, offset, count):
        end = offset + count - 1
        url, tag = version['version']
        with self.request('GET', {'Range': f'bytes={offset}-{end}', 'If-Match': tag}) as reply:
            if (reply.status != 206 or reply.geturl() != url or reply.headers.get('ETag') != tag
                    or reply.headers.get('Content-Range') != f"bytes {offset}-{end}/{version['size']}"
                    or reply.headers.get('Content-Length', str(count)) != str(count)
                    or reply.headers.get('Content-Encoding', 'identity') != 'identity'):
                raise RestartRequired('The server did not honor the verified byte range. Download from byte zero?')
            data = bytearray()
            while len(data) <= count:
                self.check()
                block = reply.read1(min(256 * 1024, count + 1 - len(data)))
                if not block:
                    break
                data.extend(block)
            if len(data) > count:
                raise RestartRequired('The server returned more than the requested range. Download from byte zero?')
            return data


class DesktopRanges:
    def __init__(self, provider, path):
        self.provider, self.path = provider, path
        self.values = session.credentials(provider.context)
        self.options = self.values[provider.remote]
        self.raw_local = None
        self.http = None
        self.backing = None
        self.crypt = self.options['type'] == 'crypt'
        options = self.options
        if self.crypt:
            from features.rclone.localcrypt.transport import CryptCommand
            commands = CryptCommand(provider.binary, provider.context, provider._cancellation,
                provider.check, closed=lambda: provider.closed, remote=provider.remote)
            path = commands.encode(path)
            backing = options['remote']
            if Path(backing).is_absolute():
                self.raw_local = Path(backing) / path
            else:
                remote, _, prefix = backing.partition(':')
                options = self.values.get(remote, {})
                path = '/'.join(p for p in (prefix.rstrip('/'), path) if p)
                if options.get('type') == 'local' and Path(path).is_absolute():
                    self.raw_local = Path(path)
                elif options.get('type') in ('s3', 'drive', 'onedrive', 'dropbox', 'smb', 'webdav'):
                    self.backing = (CryptCommand(provider.binary, provider.context, provider._cancellation,
                        provider.check, closed=lambda: provider.closed, remote=remote), path)
        if options.get('type') == 'alias' and Path(options['remote']).is_absolute():
            self.raw_local = Path(options['remote']) / path
        if options.get('type') == 'http' and set(options) == {'type', 'url'} and not self.crypt:
            url = urlsplit(options['url'])
            if url.scheme in ('https', 'http') and url.netloc and not (url.username or url.query or url.fragment):
                self.http = HttpRanges(options['url'].rstrip('/') + '/' + quote(path), provider.check)
        self.chunk_size = 16 * 1024 * 1024
        self.cloud_hash = not self.crypt and options.get('type') in ('s3', 'drive', 'onedrive', 'webdav')

    def stat(self):
        if self.http:
            return self.http.stat()
        if self.raw_local is not None:
            info = self.raw_local.stat()
            size = self.provider.entry(self.path)['size'] if self.crypt else info.st_size
            return dict(size=size, encoded=False, version=[info.st_dev, info.st_ino,
                        info.st_size, info.st_mtime_ns, info.st_ctime_ns])
        if self.backing:
            backing, raw_path = self.backing
            header = backing.command('cat', raw_path, '--offset', '0', '--count', '32', limit=32)
            if len(header) != 32 or not header.startswith(b'RCLONE\x00\x00'):
                raise ValueError('Invalid encrypted source header.')
            row = self.provider.entry(self.path)
            return dict(size=row['size'], encoded=False, version=[header.hex(), row['modified']])
        if self.cloud_hash:
            row = json.loads(self.provider.command('lsjson', self.path, '--stat', '--hash', '--no-mimetype'))
            hashes = {key.lower(): value for key, value in (row.get('Hashes') or {}).items()}
            for algorithm, digits in (('sha256', 64), ('sha1', 40), ('md5', 32)):
                checksum = hashes.get(algorithm, '')
                if re.fullmatch('[0-9a-fA-F]{%d}' % digits, checksum) and row['Size'] >= 0:
                    return dict(size=row['Size'], encoded=False, version=row.get('ID'),
                                algorithm=algorithm, checksum=checksum.lower())
        raise RestartRequired('This source has no supported version and byte-range combination. Download from byte zero?')

    def read(self, version, offset, count):
        if self.http:
            return self.http.read(version, offset, count)
        self.provider.check()
        if (self.raw_local is not None or self.backing) and self.stat() != version:
            raise ValueError('The source changed. Inspect the interrupted download.')
        return self.provider.command('cat', self.path, '--offset', str(offset), '--count', str(count), limit=count)
