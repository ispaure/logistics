"""Archive workspace and browser capabilities; UI imports remain lazy."""


def register():
    from commonUtils.features import BrowserExtension, SelectionAction
    from commonUtils.fileUtils import File
    from commonUtils.dirUtils import Directory
    from features.contributions import Feature, PageContribution
    return Feature(id='archives', label='Archives', pages=[
        PageContribution('Archives', 'archives.workspace', create_page, order=12, navigation_icon='archives'),
    ], browser=BrowserExtension(actions=[
        SelectionAction('manage_archive', 'Open archive manager…', (File,), _manage, order=40,
                        is_available=lambda context: len(context.paths) == 1 and _supported(context.paths[0])),
        SelectionAction('create_archive', 'Create archive…', (File, Directory), _new_archive, order=45),
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


def create_page(parent=None):
    from .ui.page import ArchivePage
    return ArchivePage(parent)


def _supported(path):
    return str(path).lower().endswith(('.zip', '.cbz', '.tar', '.tar.gz', '.tgz', '.tar.xz', '.txz', '.tar.bz2', '.tbz2'))


def _workspace(context):
    from commonUtils.ui import pyside as qt
    from .ui.page import ArchivePage
    host = context.host or context.browser
    # Prefer the contributed workspace in the current Logistics window.
    for window in [host.window(), *qt.QApplication.topLevelWidgets()]:
        for page in window.findChildren(ArchivePage):
            parent = page.parentWidget()
            while parent is not None:
                if isinstance(parent, qt.QTabWidget) and parent.indexOf(page) >= 0:
                    parent.setCurrentWidget(page)
                    window.show()
                    window.raise_()
                    return page
                parent = parent.parentWidget()
    # Standalone file browsers use a retained, safely closing workspace window.
    from .ui.window import ArchiveWindow
    window = ArchiveWindow()
    window.show()
    return window.page


def _manage(context):
    paths = [path for path in context.paths if _supported(path)]
    if not paths:
        return
    _workspace(context).open_archive(paths[0])
    if len(paths) > 1:
        from .ui.window import ArchiveWindow
        for path in paths[1:]:
            window = ArchiveWindow()
            window.show()
            window.page.open_archive(path)


def _new_archive(context):
    _workspace(context).new_archive(sources=context.paths)
