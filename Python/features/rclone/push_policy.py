"""Push-only nuisance filters and fail-closed LocalCrypt preflight."""
import json
import os
from pathlib import Path
import stat
from commonUtils.persistence import atomic_write_json
from commonUtils.persistence.publication import mutation_lock
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.resource_mutations import delete_resource, inventory
from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
from . import configuration, session

# Exact generated file names only. User exclusion patterns never authorize deletion.
CLEANUP_NAMES = frozenset({'.ds_store', 'thumbs.db', 'ehthumbs.db', 'ehthumbs_vista.db'})
DEFAULT_EXCLUDES = ('.DS_Store', '[Tt]humbs.db', '[Ee]hthumbs.db', '[Ee]hthumbs_vista.db', '[Dd]esktop.ini', '._*')


def settings_path():
    return configuration.get_rclone_config_dir() / 'push-rules.json'


def validate_excludes(values):
    if not isinstance(values, (list, tuple)) or len(values) > 200:
        raise ValueError('Use at most 200 exclusion patterns.')
    result = []
    for value in values:
        if not isinstance(value, str) or len(value) > 1024 or any(ord(c) < 32 for c in value):
            raise ValueError('Each exclusion must be a single pattern, at most 1024 characters.')
        value = value.strip()
        if value and value not in result:
            result.append(value)
    return tuple(result)


def load_excludes():
    path = settings_path()
    if not path.exists():
        return DEFAULT_EXCLUDES
    if path.stat().st_size > 256 * 1024:
        raise ValueError('Push exclusions settings are too large.')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('schema') != 1:
        raise ValueError('Invalid push exclusions settings. Review rclone settings.')
    return validate_excludes(data.get('excludes'))


def save_excludes(values):
    values = validate_excludes(values)
    settings_path().parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(settings_path(), {'schema': 1, 'excludes': list(values)}, durable_directory=True)


def _inventory(root, cancelled):
    records = {}
    def failed(error):
        raise error
    for folder, directories, files in os.walk(root, followlinks=False, onerror=failed):
        check_cancelled(cancelled)
        for name in (*directories, *files):
            path = Path(folder) / name
            info = path.lstat()
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise ValueError('LocalCrypt push refused: linked entry ' + str(path.relative_to(root)))
            if not stat.S_ISDIR(info.st_mode) and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                raise ValueError('LocalCrypt push refused: unsupported entry ' + str(path.relative_to(root)))
            records[path.relative_to(root).as_posix()] = (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    return records


def validate_localcrypt_push(item, binary, *, cancelled=lambda: False, report=lambda *args: None, cleanup=True):
    """Verify every physical name and decrypt/authenticate every file in memory.

    Filters cannot hide invalid files. Preview does not delete generated files;
    real pushes remove only the exact allowlist of independent regular files.
    """
    from .local_crypt import CryptResources, unlock
    with mutation_lock:
        check_cancelled(cancelled)
        if not item.data.is_dir():
            raise ValueError('LocalCrypt push source is missing.')
        resolved_root = item.data.resolve(strict=True)
        root_identity = (item.data.stat().st_dev, item.data.stat().st_ino)
        if str(unlock(item)[item.remote].get('no_data_encryption', 'false')).lower() in {'true', '1', 'yes'}:
            raise ValueError('LocalCrypt push requires content encryption; no_data_encryption is enabled.')
        original = _inventory(item.data, cancelled)
        removed = 0
        for name, stamp in original.items():
            check_cancelled(cancelled)
            if Path(name).name.casefold() in CLEANUP_NAMES and stat.S_ISREG(stamp[2]):
                path = item.data / name
                with path.open('rb') as stream:
                    if stream.read(8) == b'RCLONE\x00\x00':
                        continue  # Resolve encrypted names through the provider below.
                if not cleanup:
                    raise ValueError('LocalCrypt contains generated junk. A real push will remove it before validation: ' + name)
                info = path.lstat()
                if (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != stamp:
                    raise ValueError('LocalCrypt changed during cleanup. Retry the push.')
                path.unlink()
                removed += 1
        before = _inventory(item.data, cancelled)
        for name, stamp in before.items():
            check_cancelled(cancelled)
            if stat.S_ISREG(stamp[2]):
                with (item.data / name).open('rb') as stream:
                    header = stream.read(32)
                if len(header) != 32 or header[:8] != b'RCLONE\x00\x00':
                    raise ValueError('LocalCrypt push refused: file is not encrypted: ' + name)
        provider = CryptResources(item, binary=binary)
        try:
            expected = set()
            decoded_files = set()
            encrypted_junk = []
            pending = ['']
            with provider.operation(cancelled):
                while pending:
                    directory = pending.pop()
                    report(len(expected), 0, f'Validating encrypted names… ({removed} generated files removed)')
                    for row in provider.list(directory, cancelled=cancelled):
                        physical = provider._physical(row['path'], row['directory']).relative_to(item.data).as_posix()
                        if physical in expected:
                            raise ValueError('LocalCrypt has ambiguous encoded names.')
                        expected.add(physical)
                        if row['directory']:
                            pending.append(row['path'])
                        else:
                            decoded_files.add(row['path'])
                            if row['name'].casefold() in CLEANUP_NAMES:
                                if not cleanup:
                                    raise ValueError('LocalCrypt contains encrypted generated junk. A real push will remove it: ' + row['path'])
                                encrypted_junk.append((physical, row['path'], inventory(provider, row['path'], cancelled=cancelled)))
                unexpected = set(before) - expected
                if unexpected or expected - set(before):
                    names = ', '.join(sorted(unexpected or expected - set(before))[:5])
                    raise ValueError('LocalCrypt push refused: names do not match the crypt settings: ' + names)
                report(0, 0, 'Authenticating all encrypted file contents…')
                environment, remote, _ = session.launch(provider.context, 'view:', '')
                output = run_bytes([str(binary), '--config', session.NULL_CONFIG, '--log-level', 'ERROR',
                                    '--retries', '1', '--low-level-retries', '1', 'hashsum', 'SHA256', remote,
                                    '--download', '--checkers', '1'], environment=environment,
                                   max_output=64 * 1024 * 1024, timeout=24 * 60 * 60, cancelled=cancelled)
                hashed = set()
                for line in output.decode('utf-8').splitlines():
                    digest, separator, name = line.partition('  ')
                    if not separator or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                        raise ValueError('LocalCrypt content verification returned an invalid result.')
                    hashed.add(name)
                if hashed != decoded_files:
                    raise ValueError('LocalCrypt push refused: not every file could be authenticated.')
            if (item.data.resolve(strict=True) != resolved_root
                    or (item.data.stat().st_dev, item.data.stat().st_ino) != root_identity
                    or _inventory(item.data, cancelled) != before):
                raise ValueError('LocalCrypt changed during verification. Retry the push.')
            # Authenticate first, then delete through the same version-checked
            # provider operation as the file browser. A junk name cannot hide
            # corrupted ciphertext or authorize deleting a directory.
            for physical, path, snapshot in encrypted_junk:
                report(removed, 0, 'Removing encrypted generated junk…')
                with provider.operation(cancelled):
                    delete_resource(provider, path, expected=snapshot, cancelled=cancelled)
                del before[physical]
                removed += 1
            after = _inventory(item.data, cancelled)
            # Removing a child changes its parent's size/timestamps. Membership,
            # directory identity and all remaining file versions must still match.
            unchanged = set(after) == set(before) and all(
                after[name][:3] == stamp[:3] if stat.S_ISDIR(stamp[2]) else after[name] == stamp
                for name, stamp in before.items())
            if (not unchanged or item.data.resolve(strict=True) != resolved_root
                    or (item.data.stat().st_dev, item.data.stat().st_ino) != root_identity):
                raise ValueError('LocalCrypt changed during cleanup. Retry the push.')
            return removed
        except OSError as error:
            raise ValueError('LocalCrypt push refused: a file could not be decrypted and authenticated. Check for plaintext, corruption or incorrect keys.') from error
        finally:
            provider.close()
