"""AES ZIP creation capabilities shared with the Comics feature."""


def register():
    from commonUtils.features import BrowserExtension, SelectionAction
    from commonUtils.fileUtils import File
    from commonUtils.dirUtils import Directory
    from features.contributions import Feature
    return Feature(id='archives', label='Archives', browser=BrowserExtension(actions=[
        SelectionAction('create_encrypted_zip', 'Create encrypted ZIP…', (File, Directory), _create_zip, order=50)
    ]))


def _create_zip(context):
    from .ui.create_zip import CreateZipDialog
    dialog = CreateZipDialog(context.paths, parent=context.host or context.browser)
    try:
        return dialog.exec()
    finally:
        dialog.deleteLater()
        context.browser.refresh()
