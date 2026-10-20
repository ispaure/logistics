"""Actual workflow screenshots in a disposable synthetic native test workspace."""
import asyncio
from commonUtils.runtime.platform import get_os, OS


async def exercise_ui_review(app):
    import base64
    import toga
    webp = base64.b64decode('UklGRhwAAABXRUJQVlA4TA8AAAAvAYAAEAcQ/Y8CBiKi/wEA')
    variants = [webp,
        base64.b64decode('UklGRjwAAABXRUJQVlA4IDAAAADQAQCdASoCAAMAAUAmJaACdLoB+AADsAD+8ut//NgVzXPv9//S4P0uD9Lg/9KQAAA='),
        base64.b64decode('UklGRl4AAABXRUJQVlA4WAoAAAAQAAAAAQAAAgAAQUxQSAcAAAAAgICAgICAAFZQOCAwAAAA0AEAnQEqAgADAAFAJiWgAnS6AfgAA7AA/vLrf/zYFc1z7/f/0uD9Lg/S4P/SkAAA')]
    from features.images.validation import image_dimensions
    from services.documents.readers import PrivateReader
    from commonUtils.runtime.document_access import LocalDocuments
    from zipfile import ZipFile
    from .reader_checks import wait_for_reader, assert_comic_centered
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
    from unittest.mock import patch
    # Decoder dimensions refer to individual pages; automatic tablet spreads
    # are exercised separately by reader/layout checks.
    with patch.dict(app.preferences.values, comic_layout='single'):
        await app.open_book(record['id'])
        assert app.reader_manager().active.book_reader is not None, app.reader_manager().active.book_status.text
        for index in range(len(variants)):
            await app.readers.active.display_book_page(index)
            image = app.reader_manager().active.book_content.children[0].image
            assert (image.width, image.height) == (2, 3)
    assert comic.read_bytes() == original
    app.readers.close(app.readers.active.session.id)
    print('LOGISTICS_UI_REVIEW=started', flush=True)
    screenshots = []
    toolbar_checks = []
    async def capture(name):
        print('LOGISTICS_UI_REVIEW=begin:' + name, flush=True)
        await asyncio.sleep(.4)
        if get_os() is OS.IOS:
            group = getattr(app, '_reader_toolbar_group', None)
            window = group.window if group is not None else None
            window = window() if callable(window) else window
            children = group.subviews if group is not None else []
            children = children() if callable(children) else children
            if window is not None and len(children):
                group.layoutIfNeeded()
                frames = [(float(button.frame.origin.x), float(button.frame.size.width))
                          for button in children]
                assert all(width >= 40 and abs(x - 44 * index) < 1
                           for index, (x, width) in enumerate(frames)), (name, frames)
                toolbar_checks.append(name)
        path = app.storage_root / ('ui-review-' + name + '.png')
        from .fixtures import capture_window
        await capture_window(app, path)
        screenshots.append(str(path))
        print('LOGISTICS_UI_REVIEW=done:' + name, flush=True)

    # Earlier preference regressions deliberately use very large fonts.
    # Review representative screens at the shipped default instead.
    from logisticsmobile.preferences import DEFAULTS
    app.preferences.save(font_size=DEFAULTS['font_size'])
    await app.open_book(record['id'])
    def current_canvas():
        displayed = app.reader_manager().active.book_content.children[0]
        return displayed.canvases[0] if hasattr(displayed, 'canvases') else displayed
    owner = app.reader_manager().active
    await wait_for_reader(owner)
    await assert_comic_centered(current_canvas, fullscreen=True)
    await capture('comic-page')
    def canvas_height():
        native = current_canvas()._impl.native
        return native.bounds.size.height if get_os() is OS.IOS else native.getHeight()
    full_height = canvas_height()
    if get_os() is OS.IOS:
        assert app.native_host.adapter.controller.isTabBarHidden(), f'Fullscreen lost: {app._comic_chrome_hidden}, detail={app.adaptive.in_detail}, owner={app.readers.active.reader_immersive}'
    current_canvas().toggle_controls()
    assert not owner.reader_immersive, 'Comic controls did not open'
    deadline = asyncio.get_running_loop().time() + 15
    while canvas_height() >= full_height:
        assert asyncio.get_running_loop().time() < deadline, ('Comic mode did not reclaim reading space', full_height, canvas_height())
        await asyncio.sleep(.1)
    await wait_for_reader(owner)
    await capture('comic-controls')
    if get_os() is OS.IOS:
        assert not app.native_host.adapter.controller.isTabBarHidden()
    assert canvas_height() < full_height, 'Comic mode did not reclaim reading space'
    current_canvas().toggle_controls()
    app.show_home()
    assert not app._comic_chrome_hidden, 'Navigation stayed hidden outside the reader'
    app.readers.close(app.readers.active.session.id)
    app.create_chosen_document('md')
    app.name.value = 'Weekend notes.md'
    app.editor.value = '# Weekend\n\nA draft to continue later.\n'
    app.create_chosen_document('md')
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
    if get_os() is OS.IOS:
        from rubicon.objc import SEL
        native = app.editor._impl.native
        assert native.contentInsetAdjustmentBehavior == 2, 'Editor applied automatic insets twice'
        for edge in ('topEdgeEffect', 'bottomEdgeEffect'):
            if native.respondsToSelector(SEL(edge)):
                assert getattr(native, edge).isHidden(), 'Scroll-edge effect can cover typed text'
        native.insertText('\nKeyboard visibility check')
        await capture('editor-typing')
        assert app.store.open(app.current.id).text == app.editor.value
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
        if isinstance(widget, toga.Button) and widget.text.partition('\n')[0] == 'Workspaces':
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
            from rubicon.objc import CGPoint, ObjCClass
            # Earlier cases populate Recent. On compact iPhones the Folder
            # Hub action can be below the Home scroll viewport.
            ancestor = native.superview
            while ancestor is not None:
                if callable(ancestor):
                    ancestor = ancestor()
                if ancestor is None:
                    break
                if ancestor.isKindOfClass(ObjCClass('UIScrollView')):
                    ancestor.scrollRectToVisible(native.convertRect(native.bounds, toView=ancestor), animated=False)
                    break
                ancestor = ancestor.superview
            await asyncio.sleep(.2)
            window = app.main_window._impl.native
            point = native.convertPoint(CGPoint(native.bounds.size.width / 2, native.bounds.size.height / 2), toView=window)
            hit = window.hitTest(point, withEvent=None)
            assert hit is not None and (hit == native or hit.isDescendantOfView(native)), f'Home Browse tap blocked at {point}: {hit}'
            from toga_iOS.libs import UIControlEventTouchUpInside
            native.sendActionsForControlEvents(UIControlEventTouchUpInside)
        else:
            assert native.isShown() and native.isEnabled()
            assert native.performClick()
        for _ in range(80):
            if app.native_host.state.destination == 'files' and hasattr(app, 'folder_buttons'):
                break
            await asyncio.sleep(.05)
        assert app.native_host.state.destination == 'files'
        assert 'All files' in app.folder_picker_choices
        if leave == app.show_settings:
            await capture('folder-picker')
        assert not hasattr(app, 'folder_refresh_button')
        for source, action in (('rclone', None),
                               ('Network shares', app.folder_add_share_button), ('Local', None)):
            app.folder_source_buttons[source].on_press()
            assert list(app.folder_source_actions.children) == ([action] if action is not None else [])
            assert bool(app.folder_picker_header.children) == (source == 'rclone')
            assert all(button.enabled for button in app.folder_source_buttons.values())
            assert not app.folder_loading_box.children
        folder = app.folder_buttons['All files']
        indicator = next(child for child in folder.parent.children
                         if getattr(child, 'control_icon', '') == 'folder')
        if get_os() is OS.IOS:
            assert indicator._impl.native.imageForState(0) is not None
            folder._impl.native.sendActionsForControlEvents(UIControlEventTouchUpInside)
        else:
            assert indicator._impl.native.getCompoundDrawables()[0] is not None
            assert folder._impl.native.performClick()
        for _ in range(100):
            if getattr(app, 'files_view', None) in app.body.children:
                break
            await asyncio.sleep(.05)
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
        from android.view import WindowManager
        attributes = native.getWindow().getAttributes()
        assert attributes.flags & WindowManager.LayoutParams.FLAG_DIM_BEHIND
        assert abs(attributes.dimAmount - .5) < .01
        await capture('transfer-confirmation')
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
    browser.open_search()
    await asyncio.sleep(.2)
    header_controls = (browser.location_bar.parent_button, browser.search_button)
    if get_os() is OS.IOS:
        viewport = browser.widget.root._impl.container.native
        for control in (browser.search, browser.close_search_button, *header_controls):
            native = control._impl.native
            rect = native.convertRect(native.bounds, toView=viewport)
            assert rect.origin.x >= -1 and rect.origin.x + rect.size.width <= viewport.bounds.size.width + 1, f'Browser control clipped: {type(control).__name__}: {rect}; viewport={viewport.bounds}'
    else:
        from java import jarray, jint
        viewport = app.main_window._impl.container.native_content
        origin = jarray(jint)(2)
        viewport.getLocationOnScreen(origin)
        controls = [browser.search, browser.close_search_button, *header_controls]
        controls.extend(child for row in browser.items.children if isinstance(row, toga.Box)
                        for child in row.children[0].children if isinstance(child, toga.Button))
        for control in controls:
            native = control._impl.native
            position = jarray(jint)(2)
            native.getLocationOnScreen(position)
            x = position[0] - origin[0]
            assert x >= -1 and x + native.getWidth() <= viewport.getWidth() + 1, f'Android browser control clipped: {control}: {x}, {native.getWidth()}, viewport={viewport.getWidth()}'
        density = viewport.getResources().getDisplayMetrics().density
        for control in (*header_controls, browser.close_search_button):
            assert control._impl.native.getWidth() / density >= 44, 'Browser icon hit target too narrow'
    assert [control.control_icon for control in (*header_controls, app.file_actions_button)] == ['up', 'find', 'more']
    browser.close_search()
    while browser.tasks:
        await asyncio.gather(*tuple(browser.tasks))
    assert all(not button.text.startswith('✓') for button in browser.buttons.values())
    for row in browser.items.children:
        if isinstance(row, toga.Box):
            assert len(row.children) == 1, 'Browser added a redundant detail row'
            assert not any(isinstance(child, toga.Label) and child.text == 'Folder' for child in row.children[0].children)
    await capture('files')
    browser = app.file_browser
    entry = next(item for item in browser.entries if item.label == 'Meeting notes.md')
    await browser.activate_entry(entry)
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
    assert app.transfer_view.content.children[0].text == 'Transfer details'
    assert not any(getattr(child, 'text', '') == 'Choose a remote to pull' for child in app.transfer_view.content.children)
    assert app.cloud_remote not in app.cloud_view.children
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
            traits = native.traitCollection
            actual = native.textColor.resolvedColorWithTraitCollection(traits)
            from logisticsmobile.appearance import apple_color
            expected = apple_color('text').resolvedColorWithTraitCollection(traits)
            background = apple_color('surface').resolvedColorWithTraitCollection(traits)
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
        await browser.activate_entry(entry)
        owner = app.private_sessions.active
        editor_contrast(owner.crypt_text)
        await capture('local-editor-' + mode)
        owner.toggle_private_preview()
        await capture('local-markdown-' + mode)
        app.private_sessions.close(owner.session.id, discard=True)
        app.show_home()
        if get_os() is OS.IOS:
            from rubicon.objc import ObjCClass
            from logisticsmobile.appearance import apple_color
            native = app.home_continue._impl.native
            traits = native.traitCollection
            assert native.backgroundColor.resolvedColorWithTraitCollection(traits).isEqual(
                apple_color('surface').resolvedColorWithTraitCollection(traits))
            stroke = ObjCClass('UIColor').colorWithCGColor(native.layer.borderColor)
            assert stroke.isEqual(apple_color('border').resolvedColorWithTraitCollection(traits))
        await capture('home-' + mode)
        app.show_locations()
        await capture('folder-picker-' + mode)
        await app.show_files()
        await app.browser_file_location(('Local files', 'UI Review'))
        await capture('files-' + mode)
        app.show_settings()
        await capture('settings-' + mode)
        app.settings_navigation.choose('Workspaces')
        await capture('settings-folder-hub-' + mode)
    if get_os() is OS.IOS:
        app.main_window._impl.native.overrideUserInterfaceStyle = 0
    else:
        from android.app import UiModeManager
        from android.content import Context
        app._impl.native.getSystemService(Context.UI_MODE_SERVICE).setApplicationNightMode(UiModeManager.MODE_NIGHT_AUTO)
    from .workspace_checks import exercise_workspace
    workspace = await exercise_workspace(app)
    return {**workspace, 'screenshots': screenshots, 'reader_toolbar_checks': toolbar_checks, 'tap_to_open_tested': True,
            'provider_preview_cleanup_tested': True, 'light_dark_contrast_tested': True, 'theme_change_retains_drafts': True, 'synthetic_workspace': True}
