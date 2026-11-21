"""Qt's filesystem drag payload and the boundary with native file managers."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import sys
from pathlib import Path

from commonUtils.filesystem.local_access import check_local_path
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.drag_drop import MIME, SESSION


def local_drag_paths(mime):
    urls = mime.urls()
    if not urls or any(not url.isValid() or not url.isLocalFile() for url in urls):
        return ()
    names = [url.toLocalFile() for url in urls]
    if any('\x00' in name or not Path(name).is_absolute() or not Path(name).name for name in names):
        return ()
    return tuple(dict.fromkeys(Path(name) for name in names))


def native_drop_action(event, paths, directory, *, protected=False, platform=None):
    """Choose the operation Logistics will perform after accepting local URLs."""
    platform = platform or sys.platform
    flags = qt.Qt.KeyboardModifier
    actions = qt.Qt.DropAction
    modifiers = event.modifiers()
    if platform == 'darwin':
        # Qt maps Command to ControlModifier on macOS.
        copy, move = bool(modifiers & flags.AltModifier), bool(modifiers & flags.ControlModifier)
    else:
        copy, move = bool(modifiers & flags.ControlModifier), bool(modifiers & flags.ShiftModifier)
    if copy and move:
        return actions.IgnoreAction
    if copy or move:
        action = actions.CopyAction if copy else actions.MoveAction
    elif event.proposedAction() == actions.LinkAction:
        return actions.IgnoreAction
    elif protected or not event.possibleActions() & actions.MoveAction:
        action = actions.CopyAction
    elif platform in ('darwin', 'win32'):
        try:
            volume = directory.stat().st_dev
            same_volume = all(path.lstat().st_dev == volume for path in paths)
        except OSError:
            same_volume = False
        action = actions.MoveAction if same_volume else actions.CopyAction
    else:
        action = event.proposedAction()
    return action if event.possibleActions() & action else actions.IgnoreAction


class LocalFileDrag(qt.QMimeData):
    def __init__(self, paths, *, internal=False):
        super().__init__()
        self.handled = False
        self.setUrls([qt.QUrl.fromLocalFile(str(path)) for path in paths])
        if internal:
            self.setData(MIME, SESSION)


def start_file_drag(widget, paths, *, internal=False):
    """Give the file manager real, durable paths. The receiver owns the transfer."""
    for path in paths:
        check_local_path(path, recursive=True)
        path.lstat()
    mime = LocalFileDrag(paths, internal=internal)
    drag = qt.QDrag(widget)
    drag.setMimeData(mime)
    actions = qt.Qt.DropAction
    offered = actions.CopyAction | actions.MoveAction if internal else actions.CopyAction
    try:
        action = drag.exec(offered, actions.CopyAction)
        return None if mime.handled else action
    finally:
        drag.deleteLater()


def handoff_message(action):
    if action == qt.Qt.DropAction.IgnoreAction:
        # Cocoa can return IgnoreAction after the receiving app moves or copies
        # local URLs. It also returns IgnoreAction for a cancelled drag.
        if qt.QApplication.platformName() == 'cocoa':
            return 'Check the file manager for progress, conflicts and the outcome.'
        return 'No file-manager handoff was accepted.'
    if action is not None:
        return 'Drop accepted. Check the file manager for progress, conflicts and the outcome.'
    return ''
