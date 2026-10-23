"""Application-lifetime credential access and bounded ZIP decoding."""
from configparser import ConfigParser
import io
import os
from pathlib import Path
import re

from .credential_sessions import CredentialSessions

# rclone compares Go's Windows null-device spelling case-sensitively.
NULL_CONFIG = 'NUL' if os.name == 'nt' else os.devnull

# All application providers share this registry; isolated registries are available
# for tests or independent hosts without changing process credentials.
registry = CredentialSessions()
on_forget = registry.on_forget
remember = registry.remember
names = registry.names
paths = registry.paths
forget = registry.forget
revocation_check = registry.revocation_check
launch = registry.launch
credentials = registry.credentials
package_path = registry.package_path


def read_package(path, password):
    from commonUtils.archives.zip_access import open_archive, validate_members
    pending = {}
    total = 0
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Credential ZIPs are limited to 1 MiB.')
    with open_archive(path, password=password) as archive:
        validate_members(archive)
        if not 0 < len(archive.infolist()) <= 64:
            raise ValueError('Credential ZIPs require 1–64 entries.')
        for member in archive.infolist():
            if member.is_dir():
                continue
            if not member.flag_bits & 1:
                raise ValueError('Every credential TXT entry must be password-protected.')
            if Path(member.filename).suffix.lower() != '.txt' or member.file_size > 256 * 1024:
                raise ValueError('Credential ZIPs must contain small TXT files.')
            with archive.open(member) as stream:
                data = stream.read(256 * 1024 + 1)
            total += len(data)
            if len(data) > 256 * 1024 or total > 1024 * 1024:
                raise ValueError('Credential ZIP exceeds its expanded size limit.')
            parser = ConfigParser(interpolation=None)
            parser.read_file(io.StringIO(data.decode('utf-8-sig')))
            if parser.defaults() or len(parser.sections()) != 1:
                raise ValueError('Each TXT file must define one remote.')
            name = parser.sections()[0]
            values = dict(parser[name])
            if name in pending or not values.get('type') or any(not re.fullmatch(r'[a-zA-Z0-9_]+', key) for key in values):
                raise ValueError('Invalid or duplicate remote settings.')
            if any('\n' in value or '\r' in value or '\x00' in value for value in values.values()):
                raise ValueError('Invalid remote setting.')
            pending[name] = values
    if not pending:
        raise ValueError('No credential TXT files found.')
    return pending
