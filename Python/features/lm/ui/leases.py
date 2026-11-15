"""Compatibility entry point for desktop Chat edit leases."""
import warnings

from ..desktop_locks import lock_file as _lock_file


def lock_file(path):
    """Forward the former UI entry point to the desktop lock owner.

    Before: from features.lm.ui.leases import lock_file
    After: from features.lm.desktop_locks import lock_file
    """
    warnings.warn(
        'features.lm.ui.leases.lock_file is deprecated. Import '
        'features.lm.desktop_locks.lock_file and pass the same path.',
        FutureWarning, stacklevel=2)
    return _lock_file(path)
