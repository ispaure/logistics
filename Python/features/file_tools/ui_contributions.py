"""Folder context-menu tools owned by the File Tools feature."""
from commonUtils.features import BrowserExtension, SelectionAction
from commonUtils.dirUtils import Directory
from features.contributions import Feature


def _open_tool(context, dialog_class):
    dialog = dialog_class(initial_path=context.paths, parent=context.host or context.browser)
    try:
        return dialog.exec()
    finally:
        dialog.deleteLater()
        context.browser.refresh()


def _open_weird_characters(context):
    from .ui.dialogs import WeirdCharactersDialog
    return _open_tool(context, WeirdCharactersDialog)


def _open_delete_pyc(context):
    from .ui.dialogs import DeletePycDialog
    return _open_tool(context, DeletePycDialog)


def get_contributions():
    return Feature(id='file_tools', label='File Tools', browser=BrowserExtension(actions=[
        SelectionAction('weird_characters', 'List Weird Characters…', Directory,
                        _open_weird_characters),
        SelectionAction('delete_pyc', 'Bulk Delete PYC…', Directory,
                        _open_delete_pyc),
    ]))
