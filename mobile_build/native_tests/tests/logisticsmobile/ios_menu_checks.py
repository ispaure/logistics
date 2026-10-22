"""Exercise deferred folder/file callbacks in an isolated native test app."""
import asyncio


async def exercise_ios_browser_menus(app):
    """Use only a disposable app storage root; invoke the real native completions."""
    from rubicon.objc import Block, ObjCInstance, objc_id

    root = app.private_root / 'LocalFiles'
    (root / 'Menu folder').mkdir(parents=True, exist_ok=True)
    (root / 'Menu file.txt').write_text('Native menu fixture')
    await app.show_files(local_root=True)
    browser = app.file_browser
    async with asyncio.timeout(10):
        while not browser.native_list._impl.native.visibleCells:
            await asyncio.sleep(.05)
    # Menu loading selects a row and updates native cells asynchronously.
    checked = []
    for name in ('Menu folder', 'Menu file.txt', 'Menu folder'):
        native = browser.native_list._impl.native
        cell = next(cell for cell in native.visibleCells if cell.accessoryView.row.title == name)
        button = cell.accessoryView
        completed = app.loop.create_future()

        def delivered(pointer):
            children = ObjCInstance(pointer)
            completed.set_result([str(child.title) for child in children])

        completion = Block(delivered, None, objc_id)
        # Enter the provider as UIKit does, with a native completion pointer.
        # Its asynchronous loader must retain the copied Objective-C owner.
        button.menu_provider_block.func(completion.block)
        labels = await asyncio.wait_for(completed, 10)
        assert 'Open' in labels and 'Details' in labels, (name, labels)
        assert browser.selected == button.row.entry.identity
        checked.append(name)
    return checked
