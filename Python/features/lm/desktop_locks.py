"""Use QtCore's lock-file protocol for desktop Chat storage."""


def lock_file(path):
    from PySide6.QtCore import QLockFile

    return QLockFile(str(path))
