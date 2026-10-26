"""Exercise folder/file action sheets in an isolated native test app."""
import asyncio


async def exercise_ios_browser_menus(app):
    """Use disposable storage and real cells, buttons and native action sheets."""

    root = app.private_root / 'LocalFiles'
    (root / 'Menu folder').mkdir(parents=True, exist_ok=True)
    filename = 'Menu file ' + 'long filename ' * 12 + 'final.txt'
    (root / filename).write_text('Native menu fixture')
    await app.show_files(local_root=True)
    browser = app.file_browser
    async with asyncio.timeout(10):
        while not browser.native_list._impl.native.visibleCells:
            await asyncio.sleep(.05)
    # Opening the sheet selects a row without opening its contents.
    checked = []
    for name in ('Menu folder', filename, 'Menu folder'):
        native = browser.native_list._impl.native
        cell = next(cell for cell in native.visibleCells if cell.accessoryView.row.title == name)
        button = cell.accessoryView
        button.selectRow_(button)
        async with asyncio.timeout(10):
            while getattr(browser, '_item_menu', None) is None or browser._item_menu.native is None:
                await asyncio.sleep(.05)
        menu = browser._item_menu
        labels = [str(action.title) for action in menu.native.actions]
        assert 'Open' in labels and 'Details' in labels, (name, labels)
        assert str(menu.native.title) == name
        assert browser.selected == button.row.entry.identity
        await asyncio.sleep(.2)
        browser.dismiss_item_menu()
        await asyncio.sleep(.2)
        checked.append(name)
    return checked
