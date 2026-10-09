"""One Logistics process per user, including launches from different checkouts."""
from commonUtils.storage import temporary_directory
from commonUtils.ui import pyside as qt


def instance_lock():
    lock = qt.QLockFile(str(temporary_directory() / 'logistics-instance.lock'))
    # Long-lived ownership: a running app must never expire because of its age.
    # Qt detects dead process owners independently of this timeout.
    lock.setStaleLockTime(0)
    return lock
