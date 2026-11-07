"""Workspace display names; persisted source/category keys remain stable."""

RCLONE_COPIES = 'Rclone Copies'
RCLONE_REMOTES = 'Rclone Remotes'


def local_source_label(key, *, device='Computer'):
    return {'Rclone': RCLONE_COPIES, 'Others': f'On This {device}'}.get(key, key)


def encrypted_copy_label(name):
    return f'{name} - Encrypted Copy'
