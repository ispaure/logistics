"""Actual workflow screenshots in a disposable synthetic native test workspace."""
import asyncio
from pathlib import Path
from commonUtils.runtime.platform import get_os, OS


async def exercise_ui_review(app):
    import base64
    import toga
    webp = base64.b64decode('UklGRhwAAABXRUJQVlA4TA8AAAAvAYAAEAcQ/Y8CBiKi/wEA')
    variants = [webp,
        base64.b64decode('UklGRjwAAABXRUJQVlA4IDAAAADQAQCdASoCAAMAAUAmJaACdLoB+AADsAD+8ut//NgVzXPv9//S4P0uD9Lg/9KQAAA='),
        base64.b64decode('UklGRl4AAABXRUJQVlA4WAoAAAAQAAAAAQAAAgAAQUxQSAcAAAAAgICAgICAAFZQOCAwAAAA0AEAnQEqAgADAAFAJiWgAnS6AfgAA7AA/vLrf/zYFc1z7/f/0uD9Lg/S4P/SkAAA')]
    from features.comics.mobile.validation import image_dimensions
    from logisticsmobile.localcrypt import PrivateReader
    from commonUtils.runtime.document_access import LocalDocuments
    from zipfile import ZipFile
    comic = app.storage_root / 'WebP review.cbz'
    with ZipFile(comic, 'w') as archive:
        for index, data in enumerate(variants):
            assert image_dimensions(data) == (2, 3)
            image = toga.Image(src=data)
            assert (image.width, image.height) == (2, 3), 'Native WebP decoding failed'
            thumbnail = await asyncio.to_thread(app.cloud_client.request, 'image_thumbnail',
                data=base64.b64encode(data).decode(), width=20, height=30)
            cover = toga.Image(src=base64.b64decode(thumbnail['data']))
            assert (cover.width, cover.height) == (20, 30)
            archive.writestr(f'page{index + 1}.webp', data)
    original = comic.read_bytes()
    private = PrivateReader(comic.name, original)
    for index, data in enumerate(variants):
        assert private.page(index) == ('image', data)
    record = await asyncio.to_thread(app.reader_manager().catalog.library_store.import_book, LocalDocuments(), comic)
    await app.open_book(record['id'])
    assert app.reader_manager().active.book_reader is not None, app.reader_manager().active.book_status.text
    for index in range(len(variants)):
        await app.readers.active.display_book_page(index)
        image = app.reader_manager().active.book_content.children[0].image
        assert (image.width, image.height) == (2, 3)
    assert comic.read_bytes() == original
    app.readers.close(app.readers.active.session.id)
    screenshots = []
    async def capture(name):
        await asyncio.sleep(.4)
        path = app.storage_root / ('ui-review-' + name + '.png')
        if get_os() is OS.IOS:
            from rubicon.objc import Block, objc_id
            from toga_iOS.libs import UIGraphicsImageRenderer
            from toga_iOS.images import nsdata_to_bytes
            native = app.main_window._impl.native
            renderer = UIGraphicsImageRenderer.alloc().initWithSize(native.bounds.size)
            def render(context):
                native.drawViewHierarchyInRect(native.bounds, afterScreenUpdates=True)
            path.write_bytes(nsdata_to_bytes(renderer.PNGDataWithActions(Block(render, None, objc_id))))
        else:
            data = app.main_window.as_image().data
            assert data.startswith(b'\x89PNG') and len(data) > 64, 'Android screenshot was empty'
            import os
            with path.open('wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        screenshots.append(str(path))

    # Earlier preference regressions deliberately use very large fonts.
    # Review representative screens at the shipped default instead.
    from logisticsmobile.preferences import DEFAULTS
    app.preferences.save(font_size=DEFAULTS['font_size'])
    await app.open_book(record['id'])
    canvas = app.reader_manager().active.book_content.children[0]
    await capture('comic-page')
    def canvas_height():
        native = canvas._impl.native
        return native.bounds.size.height if get_os() is OS.IOS else native.getHeight()
    full_height = canvas_height()
    if get_os() is OS.IOS:
        assert app.native_host.adapter.controller.isTabBarHidden(), f'Fullscreen lost: {app._comic_chrome_hidden}, detail={app.adaptive.in_detail}, owner={app.readers.active.reader_immersive}'
    canvas.toggle_controls()
    await capture('comic-controls')
    if get_os() is OS.IOS:
        assert not app.native_host.adapter.controller.isTabBarHidden()
    assert canvas_height() < full_height, 'Comic mode did not reclaim reading space'
    canvas.toggle_controls()
    app.show_home()
    assert not app._comic_chrome_hidden, 'Navigation stayed hidden outside the reader'
    app.readers.close(app.readers.active.session.id)
    app.new_hub_document()
    app.name.value = 'Weekend notes.md'
    app.editor.value = '# Weekend\n\nA draft to continue later.\n'
    app.new_hub_document()
    app.name.value = 'Reading list.md'
    app.editor.value = '# Reading list\n\n- Finish chapter three\n- Start the next comic\n'
    app.show_home()
    await capture('home')
    app.show_documents_hub()
    await capture('documents')
    app.show_documents()
    if get_os() is OS.IOS:
        screens = app.adaptive.detail_routes if app.adaptive.split is not None else app.routes.screens['documents']
        assert str(screens[-1][2].controller.title) == app.name.value
    await capture('editor')
    app.editor.focus()
    await capture('editor-focus')
    app.show_preview()
    await capture('markdown')
    app.show_library()
    await capture('library')
    labels = app.readers.catalog.book_labels
    if labels:
        await app.open_book(next(iter(labels.values())))
        await capture('reader')
    app.show_cloud(present=False)
    restore = getattr(app, 'cloud_restore_task', None)
    if restore is not None and not restore.done():
        await restore
    await app.show_files()
    root = app.private_root / 'LocalFiles'
    folder = root / 'UI Review'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'Meeting notes.md').write_text('# Meeting notes\n\nA local Markdown file.\n', encoding='utf-8')
    (folder / 'Project brief.txt').write_text('A local text file.', encoding='utf-8')
    (folder / 'Research').mkdir(exist_ok=True)
    (folder / 'WebP comic.cbz').write_bytes(original)
    (folder / 'Cover.webp').write_bytes(webp)
    def home_browse_button(widget):
        if isinstance(widget, toga.Button) and widget.text == 'Browse files':
            return widget
        children = list(widget.children)
        if isinstance(widget, toga.ScrollContainer) and widget.content is not None:
            children.append(widget.content)
        return next((found for child in children if (found := home_browse_button(child)) is not None), None)
    for leave in (app.show_settings, app.show_documents_hub, app.show_cloud):
        await app.browser_file_location(('Local files', 'UI Review'))
        app.file_browser.search.value = 'Old filter with no matches'
        leave()
        app.show_home()
        action = home_browse_button(app.body)
        assert action is not None
        await asyncio.sleep(.2)
        native = action._impl.native
        if get_os() is OS.IOS:
            from rubicon.objc import CGPoint
            window = app.main_window._impl.native
            point = native.convertPoint(CGPoint(native.bounds.size.width / 2, native.bounds.size.height / 2), toView=window)
            hit = window.hitTest(point, withEvent=None)
            assert hit is not None and (hit == native or hit.isDescendantOfView(native)), f'Home Browse tap blocked at {point}: {hit}'
            from toga_iOS.libs import UIControlEventTouchDown
            native.sendActionsForControlEvents(UIControlEventTouchDown)
        else:
            assert native.isShown() and native.isEnabled()
            assert native.performClick()
        for _ in range(80):
            if app.native_host.state.destination == 'files' and hasattr(app, 'folder_choice'):
                break
            await asyncio.sleep(.05)
        assert app.native_host.state.destination == 'files'
        assert 'All files' in app.folder_picker_choices
        if leave == app.show_settings:
            await capture('folder-picker')
        picker = app.folder_choice
        if get_os() is OS.IOS:
            picker._impl.native.becomeFirstResponder()
            await asyncio.sleep(.1)
            assert picker._impl.native.isFirstResponder
        picker.value = 'All files'
        if get_os() is OS.IOS:
            assert not picker._impl.native.isFirstResponder, 'Folder wheel stayed open'
        if leave == app.show_settings:
            await capture('folder-options')
        await app.folder_browse_button.on_press()
        assert app.files_view in app.body.children
        assert app.file_storage.value == 'Local files' and app.file_path == ''
        assert app.file_browser.search.value == ''
        assert any(entry.label == 'UI Review' for entry in app.file_browser.entries)
    dialog = toga.ConfirmDialog('Pull folder?', 'From: Example remote:/Comics\nTo: Local/Comics\n\nLocal files may be replaced or removed. Continue?')
    pending = asyncio.create_task(app.main_window.dialog(dialog))
    await asyncio.sleep(.2)
    if get_os() is OS.IOS:
        assert [str(action.title) for action in dialog._impl.native.actions] == ['OK', 'Cancel']
        await capture('transfer-confirmation')
        dialog._impl.native.dismissViewControllerAnimated(False, completion=None)
        dialog._impl.response(False)
    else:
        native = dialog._impl.native
        assert str(native.getButton(-1).getText()) == 'OK'
        assert str(native.getButton(-2).getText()) == 'Cancel'
        assert native.isShowing()
        native.getButton(-2).performClick()
    assert not await pending
    from commonUtils.runtime.local_files import LocalFiles
    from logisticsmobile.browser_preview import callbacks
    provider = LocalFiles(root)
    thumbnail, _ = callbacks(provider, app.cloud_client)
    for filename in ('WebP comic.cbz', 'Cover.webp'):
        data = await asyncio.to_thread(thumbnail, provider.entry('UI Review/' + filename), (20, 30), lambda: False)
        image = toga.Image(src=data)
        assert (image.width, image.height) == (20, 30)
    await app.browser_file_location(('Local files', 'UI Review'))
    browser = app.file_browser
    await asyncio.sleep(.2)
    if get_os() is OS.IOS:
        viewport = browser.widget.root._impl.container.native
        for control in (browser.search, browser.options_button):
            native = control._impl.native
            rect = native.convertRect(native.bounds, toView=viewport)
            assert rect.origin.x >= -1 and rect.origin.x + rect.size.width <= viewport.bounds.size.width + 1, f'Browser control clipped: {type(control).__name__}: {rect}; viewport={viewport.bounds}'
    else:
        from java import jarray, jint
        viewport = app.main_window._impl.container.native_content
        origin = jarray(jint)(2)
        viewport.getLocationOnScreen(origin)
        controls = [browser.search, browser.options_button]
        controls.extend(child for row in browser.items.children if isinstance(row, toga.Box)
                        for child in row.children[0].children if isinstance(child, toga.Button))
        for control in controls:
            native = control._impl.native
            position = jarray(jint)(2)
            native.getLocationOnScreen(position)
            x = position[0] - origin[0]
            assert x >= -1 and x + native.getWidth() <= viewport.getWidth() + 1, f'Android browser control clipped: {control}: {x}, {native.getWidth()}, viewport={viewport.getWidth()}'
        for control in (browser.back_button, browser.options_button):
            layout = control._impl.native.getLayout()
            assert layout is not None and layout.getEllipsisCount(0) == 0, 'Browser toolbar caption truncated'
    assert all(not button.text.startswith('✓') for button in browser.buttons.values())
    for row in browser.items.children:
        if isinstance(row, toga.Box):
            assert len(row.children) == 1, 'Browser added a redundant detail row'
            assert not any(isinstance(child, toga.Label) and child.text == 'Folder' for child in row.children[0].children)
    await capture('files')
    browser = app.file_browser
    entry = next(item for item in browser.entries if item.label == 'Meeting notes.md')
    await browser._select_pressed(entry, browser.buttons[entry.identity])
    owner = app.private_sessions.active
    assert owner.crypt_reader.name == 'Meeting notes.md'
    owner.crypt_text.value = '# Meeting notes\n\nEdited while testing.\n'
    await capture('local-editor')
    owner.toggle_private_preview()
    await capture('local-markdown')
    app.show_settings()
    assert owner.crypt_text.value == '# Meeting notes\n\nEdited while testing.\n'
    assert owner.crypt_preview not in owner.crypt_content.children
    app.private_sessions.activate(owner.session.id)
    assert app.provider_sessions().active.crypt_text.value == '# Meeting notes\n\nEdited while testing.\n'
    app.private_sessions.close(owner.session.id, discard=True)
    app.show_transfers()
    await capture('transfers')
    async def appearance_mode(dark):
        if get_os() is OS.IOS:
            app.main_window._impl.native.overrideUserInterfaceStyle = 2 if dark else 1
        else:
            from android.content import Context
            from android.app import UiModeManager
            native = app._impl.native
            before = native.hashCode()
            manager = native.getSystemService(Context.UI_MODE_SERVICE)
            manager.setApplicationNightMode(UiModeManager.MODE_NIGHT_YES if dark else UiModeManager.MODE_NIGHT_NO)
            for _ in range(80):
                if bool(native.getResources().getConfiguration().uiMode & 0x30 == 0x20) == dark:
                    break
                await asyncio.sleep(.05)
            assert bool(native.getResources().getConfiguration().uiMode & 0x30 == 0x20) == dark
            assert app._impl.native.hashCode() == before, 'Theme change replaced the live activity'
            app.refresh_native_theme()
        await asyncio.sleep(.3)

    def editor_contrast(widget):
        native = widget._impl.native
        if get_os() is OS.IOS:
            from rubicon.objc import ObjCClass
            colour = ObjCClass('UIColor')
            traits = native.traitCollection
            actual = native.textColor.resolvedColorWithTraitCollection(traits)
            expected = colour.labelColor().resolvedColorWithTraitCollection(traits)
            background = colour.secondarySystemBackgroundColor().resolvedColorWithTraitCollection(traits)
            assert actual.isEqual(expected), 'Editor uses a fixed foreground colour'
            assert not actual.isEqual(background), 'Editor foreground matches its background'
        else:
            from android import R
            from com.google.android.material import R as MaterialR
            foreground = native.getCurrentTextColor()
            background = widget._impl.get_theme_color(MaterialR.attr.colorSurface)
            def luminance(value):
                values = [((value >> shift) & 255) / 255 for shift in (16, 8, 0)]
                values = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4 for channel in values]
                return sum(a * b for a, b in zip(values, (.2126, .7152, .0722)))
            pair = sorted([luminance(foreground), luminance(background)])
            assert (pair[1] + .05) / (pair[0] + .05) >= 4.5, 'Low editor text contrast'
            assert foreground == widget._impl.get_theme_color(R.attr.textColorPrimary)
            from logisticsmobile.appearance import contrast_ratio
            bar = app.native_host.adapter.bottom
            selected = bar.getItemTextColor().getColorForState([R.attr.state_checked], foreground)
            assert contrast_ratio(selected, background) >= 4.5, 'Low selected navigation label contrast'

    for dark in (True, False):
        await appearance_mode(dark)
        mode = 'dark' if dark else 'light'
        app.show_documents()
        draft = app.editor.value
        editor_contrast(app.editor)
        app.editor.focus()
        await capture('editor-' + mode)
        assert app.editor.value == draft
        await app.show_files()
        await app.browser_file_location(('Local files', 'UI Review'))
        browser = app.file_browser
        entry = next(item for item in browser.entries if item.label == 'Meeting notes.md')
        await browser._select_pressed(entry, browser.buttons[entry.identity])
        owner = app.private_sessions.active
        editor_contrast(owner.crypt_text)
        await capture('local-editor-' + mode)
        owner.toggle_private_preview()
        await capture('local-markdown-' + mode)
        app.private_sessions.close(owner.session.id, discard=True)
        app.show_home()
        await capture('home-' + mode)
        app.show_locations()
        await capture('folder-picker-' + mode)
        await app.show_files()
        await app.browser_file_location(('Local files', 'UI Review'))
        await capture('files-' + mode)
        app.show_settings()
        await capture('settings-' + mode)
    if get_os() is OS.IOS:
        app.main_window._impl.native.overrideUserInterfaceStyle = 0
    else:
        from android.app import UiModeManager
        from android.content import Context
        app._impl.native.getSystemService(Context.UI_MODE_SERVICE).setApplicationNightMode(UiModeManager.MODE_NIGHT_AUTO)
    return {'screenshots': screenshots, 'tap_to_open_tested': True,
            'provider_preview_cleanup_tested': True, 'light_dark_contrast_tested': True, 'theme_change_retains_drafts': True, 'synthetic_workspace': True}
