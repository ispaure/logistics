"""Workspace display names; persisted source/category keys remain stable."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

RCLONE_COPIES = 'Rclone Copies'
RCLONE_REMOTES = 'Rclone Remotes'


def local_source_label(key, *, device='Computer'):
    return {'Rclone': RCLONE_COPIES, 'Others': f'On This {device}'}.get(key, key)


def encrypted_copy_label(name):
    return f'{name} - Encrypted Copy'
