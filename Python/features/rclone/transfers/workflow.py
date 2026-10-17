"""Desktop execution adapter for the shared transfer review contract."""
from pathlib import Path

from features.rclone import executable
from features.rclone import session
from features.rclone.transfers import sync
from features.rclone.transfers.review import ReviewRequest
from features.rclone.transfers.review_cli import scanner
from features.rclone.transfers.transfer_options import TransferOptions


def reviewed_sync(source, destination, *, operation, config_path, crypt_item=None, before_start=lambda: None, **kwargs):
    binary = kwargs.pop('executable_path', None) or executable.ensure_rclone()
    if binary is None:
        return False
    from features.rclone.transfers.push_policy import load_excludes
    options = TransferOptions(track_renames=kwargs.get('track_renames', False),
        bw_limit=kwargs.get('bw_limit'), copy_links=kwargs.get('copy_links', True),
        excludes=load_excludes() if operation == 'Push' else ())
    path = Path(config_path)
    def stamp():
        if path.suffix == '.session':
            return session.credentials(path)
        info = path.stat()
        return info.st_ino, info.st_size, info.st_mtime_ns
    original = stamp()
    def valid():
        try:
            return original is not None and stamp() == original
        except (OSError, ValueError):
            return False
    from features.rclone.localcrypt.backend import for_path, CryptResources
    item = crypt_item or for_path(source if operation == 'Push' else destination)
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
        if item is None or operation != 'Push':
            return {}
        from features.rclone.transfers.local_policy import cleanup_candidates
        return cleanup_candidates(item.data, display, cancelled)
    try:
        request = ReviewRequest(operation, str(source), str(destination), str(config_path), options)
        from features.rclone.transfers.ui.review import confirm_review
        if not confirm_review(request, scanner(binary, source, destination, config_path, options,
                                              display_path=display, display_directory=lambda path, cancelled: display(path, cancelled, directory=True),
                                              cleanup_plan=cleanup_plan), valid):
            return False
        if not valid():
            raise ValueError('Connection changed. Review the transfer again.')
        before_start()
        return sync.rclone_sync(source, destination, config_path=config_path, executable_path=binary,
                                excludes=options.excludes, **kwargs)
    finally:
        if provider is not None:
            provider.close()
