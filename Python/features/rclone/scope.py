"""Folder-name inference, independent of either host's storage layout."""


def folder_name(name):
    if (not isinstance(name, str) or not name or name.startswith('.') or name.endswith((' ', '.'))
            or any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name)
            or name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}):
        raise ValueError('Choose a valid local folder name.')
    return name


def push_scope(local_name, remote=None, *, specific=False):
    name = folder_name(local_name)
    return (folder_name(remote), name) if specific else (name, '')


def pull_name(remote, folder='', *, crypt=False):
    return folder_name(remote if crypt else folder.rpartition('/')[2] or remote)
