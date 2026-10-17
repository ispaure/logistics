"""Conventional menus, published by the existing workspace menu router."""
from commonUtils.ui import pyside as qt


def add(view, menu, title, callback, shortcut=None):
    action = view.menus[menu].addAction(title)
    action.triggered.connect(lambda checked=False: callback())
    action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
    if shortcut is not None:
        action.setShortcut(qt.QKeySequence(shortcut))
        view.addAction(action)
    return action


def build_menus(view):
    view.menuBar().setNativeMenuBar(False)
    view.menus = {name: view.menuBar().addMenu(name) for name in ('File', 'Edit', 'View', 'Navigate', 'Project')}
    key = qt.QKeySequence.StandardKey
    for title, callback, shortcut in (
        ('Open File…', view.open_dialog, key.Open),
        ('Save', view.save_current, key.Save),
        ('Save As…', lambda: view.save_current(True), key.SaveAs),
        ('Save All', lambda: save_all(view), 'Ctrl+Alt+S'),
        ('Reload', view.reload_current, None),
        ('Close File', lambda: view.close_document(view.current), key.Close),
        ('Close All in Group', view.close_all, None),
    ):
        add(view, 'File', title, callback, shortcut)
    autosave = view.menus['File'].addMenu('Auto Save')
    group = qt.QActionGroup(view)
    group.setExclusive(True)
    for label, mode in [('Off', 'off'), ('After 1 second', 'after_delay'), ('On focus change', 'focus_change')]:
        action = autosave.addAction(label)
        action.setCheckable(True)
        action.setChecked(view.project.autosave == mode)
        group.addAction(action)
        action.triggered.connect(lambda checked=False, mode=mode: view.set_autosave(mode))
    for title, method, shortcut in (
        ('Undo', 'undo', key.Undo), ('Redo', 'redo', key.Redo),
        ('Cut', 'cut', key.Cut), ('Copy', 'copy', key.Copy), ('Paste', 'paste', key.Paste),
        ('Select All', 'selectAll', key.SelectAll),
    ):
        add(view, 'Edit', title, lambda method=method: (view.current.edit_command(method) if hasattr(view.current, 'edit_command') else getattr(view.current, method)()) if view.current else None, shortcut)
    add(view, 'Edit', 'Find / Replace', view.find, key.Find)
    for title, callback in (
        ('Split Editor Right', view.split_right), ('Move File Left', lambda: view.move(-1)),
        ('Move File Right', lambda: view.move(1)), ('Close Editor Group', view.close_group),
        ('Locate File in Browser', view.locate),
    ):
        add(view, 'View', title, callback)


def save_all(view):
    for doc in list(view.documents.values()):
        if not view.save_document(doc):
            return False
    return True


def install_project_menu(view, page):
    def destination():
        dock = page.dock_for(view)
        return dock.workspace if dock else page.workspace
    add(view, 'File', 'Open Project…', lambda: page.register_project(destination()))
    add(view, 'File', 'Close Project', lambda: page.close_project(view), 'Ctrl+Shift+W')
    add(view, 'Project', 'Project Settings / Source Paths…', lambda: page.settings(view))
    add(view, 'Project', 'Reopen Project…', lambda: page.reopen(destination()))
    add(view, 'Project', 'Remove Registration…', lambda: page.remove_registration(view))
