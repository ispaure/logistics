"""One menu definition for hosted and standalone rename tools."""
from pathlib import Path
from commonUtils.ui import pyside as qt


def build_menus(window, renamer, close=None):
    menus = {name: window.menuBar().addMenu(name) for name in ('File', 'Edit', 'View', 'Rename', 'Help')}
    bindings = []
    keys = {renamer.browse_button: qt.QKeySequence.StandardKey.Open,
            renamer.select_all_button: qt.QKeySequence.StandardKey.SelectAll,
            renamer.undo_button: qt.QKeySequence.StandardKey.Undo}
    for name, buttons in (
        ('File', (renamer.browse_button, renamer.refresh_button, renamer.load_preset_button, renamer.save_preset_button)),
        ('Edit', (renamer.select_all_button, renamer.select_none_button)),
        ('Rename', (renamer.preview_button, renamer.reset_button, renamer.undo_button, renamer.rename_button)),
    ):
        for button in buttons:
            action = menus[name].addAction(button.text(), button.click)
            if button is renamer.browse_button:
                action.setText('Open Folder…')
            if button in keys:
                action.setShortcut(qt.QKeySequence(keys[button]))
                action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
                renamer.addAction(action)
            bindings.append((action, button))
    if close is not None:
        menus['File'].addSeparator()
        menus['File'].addAction('Close', close, qt.QKeySequence(qt.QKeySequence.StandardKey.Close))
    rules = menus['View'].addAction('Show Rules', renamer.rules_toggle.toggle)
    rules.setCheckable(True)
    def update():
        for action, button in bindings:
            action.setEnabled(button.isEnabled())
            action.setText('Open Folder…' if button is renamer.browse_button else button.text())
        rules.setChecked(renamer.rules_toggle.isChecked())
    for menu in menus.values():
        menu.aboutToShow.connect(update)
    from services.documentation import open_guide
    menus['Help'].addAction('Bulk Rename Guide', lambda: open_guide(
        Path(__file__).resolve().parents[3] / 'docs/features/bulk_rename/user/user.md', parent=window.window(), detached=True, allow_new_tabs=False))
    update()
    return menus
