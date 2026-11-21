"""Exercise native folder and file cell menus in an isolated test app."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio


async def exercise_ios_browser_menus(app):
    """Use disposable storage and real cells, buttons and UIKit menu actions."""

    root = app.private_root / 'LocalFiles'
    (root / 'Menu folder').mkdir(parents=True, exist_ok=True)
    filename = 'Menu file ' + 'long filename ' * 12 + 'final.txt'
    (root / filename).write_text('Native menu fixture')
    await app.show_files(local_root=True)
    browser = app.file_browser
    async with asyncio.timeout(10):
        while not browser.native_list._impl.native.visibleCells:
            await asyncio.sleep(.05)
    from mobile.outbound_share import SEND

    # Loading a menu selects a row without opening its contents.
    checked = []
    for name in ('Menu folder', filename, 'Menu folder'):
        native = browser.native_list._impl.native
        cell = next(cell for cell in native.visibleCells if cell.accessoryView.row.title == name)
        button = cell.accessoryView
        actions = await browser.native_list.menu_provider(button.row)
        labels = [str(action.title) for action in actions]
        assert 'Open' in labels and 'Details' in labels, (name, labels)
        if name == filename:
            share = next(action for action in actions if str(action.title) == SEND)
            assert share.image is not None and 'Add to Favourites' in labels
        else:
            assert SEND not in labels and 'Add to Favourites' not in labels
        assert browser.selected == button.row.entry.identity
        browser.dismiss_item_menu()
        checked.append(name)
    return checked
