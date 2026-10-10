"""Archive workspace and declarative browser capabilities; UI imports are lazy."""


def register():
    from commonUtils.features import BrowserExtension, SelectionAction, FileActivation
    from commonUtils.fileUtils import File
    from commonUtils.dirUtils import Directory
    from features.contributions import Feature, PageContribution
    return Feature(id='archives', label='Archives', pages=[
        PageContribution('Archives', 'archives.workspace', create_page, order=12, navigation_icon='archives'),
    ], browser=BrowserExtension(actions=[
        SelectionAction('manage_archive', 'Open archive manager…', (File,), _manage, order=40,
                        is_available=_can_manage),
        SelectionAction('extract_archive', 'Extract archive…', (File,), _extract, order=42,
                        is_available=_can_manage),
        SelectionAction('create_archive', 'Create archive…', (File, Directory), _new_archive, order=45),
        SelectionAction('create_encrypted_zip', 'Create encrypted ZIP…', (File, Directory), _create_zip, order=50),
    ], activation=[FileActivation(File, _manage, is_available=_can_activate)],
       create_controller=_create_browser_controller))


def create_page(parent=None):
    from .ui.page import ArchivePage
    return ArchivePage(parent)


def _can_manage(context):
    from commonUtils.archives import is_supported_archive
    return any(is_supported_archive(path) for path in context.paths)


def _can_activate(context):
    from commonUtils.archives import is_supported_archive
    # Comic activation belongs to Comics. Archives remains an explicit CBZ action.
    return is_supported_archive(context.path) and context.path.suffix.lower() != '.cbz'


def _create_browser_controller(host):
    from .ui.browser import ArchiveBrowserController
    return ArchiveBrowserController(host)


def _controller(context):
    if context.controller is not None:
        return context.controller
    # Direct callers outside an installed binding use the same routing contract.
    return _create_browser_controller(context.host or context.browser)


def _manage(context):
    _controller(context).open(context.paths)


def _extract(context):
    _controller(context).open(context.paths, extract=True)


def _new_archive(context):
    _controller(context).create(context.paths)


def _create_zip(context):
    from .ui.create_zip import CreateZipDialog
    dialog = CreateZipDialog(context.paths, parent=context.host or context.browser)
    try:
        return dialog.exec()
    finally:
        dialog.deleteLater()
        context.browser.refresh()
