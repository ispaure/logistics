"""Use QtCore's lock-file protocol for desktop Chat storage."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"


def lock_file(path):
    from PySide6.QtCore import QLockFile

    return QLockFile(str(path))
