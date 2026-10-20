"""Desktop lock adapter; storage owns lock names and conflict policy."""


def lock_file(path):
    from PySide6.QtCore import QLockFile

    return QLockFile(str(path))
