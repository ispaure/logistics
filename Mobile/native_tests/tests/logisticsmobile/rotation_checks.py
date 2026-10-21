"""Real orientation changes must preserve routes and respect the native safe area."""
import asyncio
import json
from pathlib import Path
import sys


def panel_state(app):
    destination = app.native_host.state.destination
    body = app.body
    settings = getattr(app, 'settings_navigation', None)
    category = destination == 'settings' and settings is not None and settings.detail_requested
    route_state = tuple((key, tuple(row[0] for row in rows
                         if not (category and key == 'settings' and row[0] == 'settings-category')))
                        for key, rows in app.routes.screens.items())
    panel = ('settings-category', settings.selected) if category else tuple(id(child) for child in body.children)
    source = getattr(app, 'folder_source', None) if destination == 'files' else None
    return (destination, route_state, panel, source, getattr(app, 'file_path', None),
            content_state(app),
            tuple(row[0] for row in app.adaptive.detail_routes), app.adaptive.in_detail)



def content_state(app):
    """Layout changes must retain logical content, not just the top route."""
    from hashlib import sha256
    reader = getattr(getattr(app, 'readers', None), 'active', None)
    record = getattr(reader, 'book_record', None) or {}
    private = getattr(getattr(app, 'private_sessions', None), 'active', None)
    comic = getattr(getattr(private, 'crypt_reader', None), 'comic_navigation', None)
    editor = getattr(app, 'editor_view', None)
    text = getattr(getattr(editor, 'editor', None), 'value', '') or ''
    return (record.get('id'), record.get('position'), getattr(comic, 'page', None),
            sha256(text.encode()).hexdigest())


def pose_snapshot(app):
    if sys.platform != 'ios':
        return dict(duo_capable=False)
    from dataclasses import asdict
    from logisticsmobile.fold_layout import reserved_divisions
    regions = reserved_divisions(app.main_window)
    all_regions = reserved_divisions(app.main_window, include_inactive=True)
    status = getattr(app, '_hinge_status', 0)
    native = app.main_window._impl.native
    return dict(duo_capable=bool(status or all_regions), hinge_status=status,
                division_regions=[asdict(region) for region in regions],
                horizontal_size_class=int(native.traitCollection.horizontalSizeClass),
                vertical_size_class=int(native.traitCollection.verticalSizeClass),
                interface_orientation=int(native.windowScene.interfaceOrientation),
                width=float(native.bounds.size.width), height=float(native.bounds.size.height))



async def rotate(app, orientation):
    landscape = orientation != 'portrait'
    if sys.platform == 'ios':
        from rubicon.objc import ObjCClass
        mask = {'portrait': 2, 'landscape-left': 8, 'landscape-right': 16}[orientation]
        preferences = ObjCClass('UIWindowSceneGeometryPreferencesIOS').alloc().initWithInterfaceOrientations(mask)
        app.main_window._impl.native.windowScene.requestGeometryUpdateWithPreferences(preferences, errorHandler=None)
    else:
        app._impl.native.setRequestedOrientation({'portrait': 1, 'landscape-left': 0, 'landscape-right': 8}[orientation])
    for _ in range(60):
        await asyncio.sleep(.1)
        if sys.platform == 'ios':
            # Interface orientation is only an acknowledgement of this request,
            # never an input to production layout or an aspect-ratio assumption.
            if int(app.main_window._impl.native.windowScene.interfaceOrientation) == {'portrait': 1, 'landscape-left': 3, 'landscape-right': 4}[orientation]:
                break
        elif (app.main_window.size.width > app.main_window.size.height) == landscape:
            break
    else:
        raise AssertionError('Native rotation did not complete: ' + orientation)
    await asyncio.sleep(.6)


def safe_geometry(app):
    if sys.platform != 'ios':
        from android.graphics import Rect
        from java import jarray, jint
        native = app.body.children[0]._impl.native
        viewport = Rect()
        app._impl.native.getWindow().getDecorView().getWindowVisibleDisplayFrame(viewport)
        position = jarray(jint)(2)
        native.getLocationOnScreen(position)
        result = dict(x=int(position[0]), y=int(position[1]),
                      view_width=int(native.getWidth()), view_height=int(native.getHeight()),
                      safe_left=viewport.left, safe_right=viewport.right,
                      safe_top=viewport.top, safe_bottom=viewport.bottom)
        assert result['view_width'] > 0 and result['view_height'] > 0, result
        assert result['x'] >= viewport.left - 1, result
        assert result['x'] + result['view_width'] <= viewport.right + 1, result
        assert result['y'] >= viewport.top - 1, result
        assert result['y'] + result['view_height'] <= viewport.bottom + 1, result
        return result
    view = app.body.children[0]
    container = view._impl.container
    size = container.native.bounds.size
    insets = container.native.safeAreaInsets
    native = view._impl.native
    rect = native.convertRect(native.bounds, toView=container.native)
    result = dict(width=float(size.width), height=float(size.height),
                  left=float(insets.left), right=float(insets.right),
                  top=float(insets.top), bottom=float(insets.bottom),
                  x=float(rect.origin.x), y=float(rect.origin.y),
                  view_width=float(rect.size.width), view_height=float(rect.size.height))
    from logisticsmobile.ios_content_background import preview_edge
    edge = preview_edge(app, container)
    result['image_preview_edge'] = edge
    window = app.main_window._impl.native
    window_rect = native.convertRect(native.bounds, toView=window)
    safe = window.safeAreaInsets
    assert window_rect.origin.x >= (0 if edge == 1 else safe.left) - 1, result
    assert window_rect.origin.x + window_rect.size.width <= window.bounds.size.width - (0 if edge == 2 else safe.right) + 1, result
    assert window_rect.origin.y >= safe.top - 1, result
    # A root background/scroll surface may extend beneath the Home indicator
    # and keyboard. Fixed foreground controls have their own stricter audit.
    assert window_rect.origin.y + window_rect.size.height <= window.bounds.size.height + 1, result
    assert result['view_width'] > 0 and result['view_height'] > 0, result
    assert rect.origin.x >= (0 if edge == 1 else insets.left) - 1, result
    assert rect.origin.x + rect.size.width <= size.width - (0 if edge == 2 else insets.right) + 1, result
    assert rect.origin.y >= insets.top - 1, result
    assert rect.origin.y + rect.size.height <= size.height + 1, result
    return result


def assert_visible_controls(app):
    """Fixed controls must stay inside cutout/Home-indicator safe bounds."""
    if sys.platform != 'ios':
        return 0
    import toga
    window = app.main_window._impl.native
    safe, size = window.safeAreaInsets, window.bounds.size
    checked = (toga.Button, toga.Selection, toga.TextInput, toga.MultilineTextInput)
    count = 0
    seen = set()
    def visit(widget):
        nonlocal count
        if id(widget) in seen:
            return
        seen.add(id(widget))
        native = widget._impl.native
        owner = native.window
        owner = owner() if callable(owner) else owner
        if (isinstance(widget, checked) and owner is not None
                and owner.ptr.value == window.ptr.value and not native.isHidden()):
            rect = native.convertRect(native.bounds, toView=window)
            if rect.size.width > 0 and rect.size.height > 0:
                count += 1
                label = getattr(widget, 'accessible_name', None) or getattr(widget, 'text', type(widget).__name__)
                details = (label, float(rect.origin.x), float(rect.origin.y),
                           float(rect.size.width), float(rect.size.height))
                assert rect.origin.x >= safe.left - 1, details
                assert rect.origin.x + rect.size.width <= size.width - safe.right + 1, details
                assert rect.origin.y >= safe.top - 1, details
                assert rect.origin.y + rect.size.height <= size.height - safe.bottom + 1, details
        # Folder actions are retained Toga buttons mounted into UIKit's bar.
        # They no longer have a parent in the Toga content tree.
        for control in getattr(widget, 'title_actions', ()):
            visit(control)
        # Scrollable form content is deliberately allowed beyond its viewport.
        if not isinstance(widget, toga.ScrollContainer):
            for child in widget.children:
                visit(child)
    visit(app.body)
    return count


async def exercise_rotation(app, *, record=None, cycles=2, panels=None):
    samples = []
    captured = set()
    async def check(name):
        if panels is not None and name not in panels:
            return
        await asyncio.sleep(.4)
        print('LOGISTICS_ROTATION_PANEL=' + name, flush=True)
        expected = panel_state(app)
        for cycle in range(cycles):
            for orientation in ('portrait', 'landscape-left', 'portrait', 'landscape-right', 'portrait'):
                await rotate(app, orientation)
                actual = panel_state(app)
                assert actual == expected, (name, orientation, expected, actual)
                sample = dict(panel=name, cycle=cycle, orientation=orientation,
                              pose=pose_snapshot(app), **safe_geometry(app))
                sample['fixed_controls'] = assert_visible_controls(app)
                if sys.platform == 'ios' and name in ('folder', 'nested-folder', 'home-file-picker'):
                    assert sample['fixed_controls'] >= 1, ('No mounted controls audited', name)
                samples.append(sample)
                print('LOGISTICS_ROTATION_SAMPLE=' + json.dumps(sample), flush=True)
                if record:
                    record(samples)
                    key = (name, orientation)
                    if cycle == 0 and key not in captured:
                        from .fixtures import capture_window
                        captured.add(key)
                        await capture_window(app, Path(app.paths.cache) / f'rotation-{name}-{orientation}.png')
    app.show_locations()
    await check('workspaces')
    for source in ('rclone', 'Network shares', 'Local'):
        app.change_folder_source(source)
        assert app.folder_source == source
        await check('workspace-' + source)
    from features.rclone.mobile.storage_location import collection_path
    root = collection_path(app.private_root) / 'Rotation fixture'
    (root / 'Child').mkdir(parents=True, exist_ok=True)
    (root / 'Child' / 'Note.md').write_text('# Rotation fixture\n\nRetain this panel.')
    await app.show_files(location=('Local files', root.name))
    await check('folder')
    await app.browser_file_folder(next(row for row in app.file_rows.values() if row['name'] == 'Child'))
    await check('nested-folder')
    app.show_home()
    await check('home')
    app.show_documents_hub()
    await check('documents')
    app.show_chat()
    await check('chat')
    app.show_chat_configuration()
    await check('chat-configuration')
    app.show_settings()
    await check('settings')
    app.settings_navigation.choose('Text')
    await check('settings-text')
    app.routes.back()
    app.settings_navigation.choose('About')
    await check('settings-about')
    app.show_cloud_connections()
    await check('connections')
    app.show_home()
    assert await app.open_hub_file()
    await check('home-file-picker')
    app.adaptive.browser('home').cancel_browser()
    document = app.store.create('Rotation.md', b'# Rotation\n\nRetain this document.')
    app.open_document(document.id)
    app.show_documents(destination='home')
    await check('markdown-preview')
    app.show_documents(edit=True, destination='home')
    await check('text-editor')
    app.show_home()
    from .fixtures import make_books
    from commonUtils.runtime.document_access import LocalDocuments
    fixtures = root / 'Readers'
    fixtures.mkdir(exist_ok=True)
    epub, comic = make_books(fixtures)
    for path, name in ((epub, 'epub'), (comic, 'comic')):
        store = app.reader_manager().catalog.library_store
        book = store.import_book(LocalDocuments(), path)
        await app.open_book(book['id'])
        owner = app.readers.active
        if name == 'comic':
            owner.set_reading_mode(False)
        await check(name)
        app.show_home()
    from commonUtils.runtime.local_files import LocalFiles
    from features.text_editor.resources import LocalTextCopies
    app.show_home()
    assert await app.open_crypt(copies=LocalTextCopies(LocalFiles(root / 'Child')), key='Note.md')
    await check('provider-markdown')
    owner = app.private_sessions.active
    owner.toggle_private_preview()
    await check('provider-text-editor')
    app.show_home()
    from types import SimpleNamespace
    from services.documents.readers import PrivateReader
    def open_archive(key, **kwargs):
        reader = PrivateReader(key, (fixtures / key).read_bytes())
        reader.key = key
        return reader
    copies = SimpleNamespace(root=fixtures, provider=LocalFiles(fixtures),
                             encrypted=False, offline=True, open=open_archive)
    assert await app.open_crypt(copies=copies, key=epub.name), app.cloud_status.value
    await check('provider-epub')
    owner = app.private_sessions.active
    owner.show_provider_epub_find()
    await check('provider-epub-find')
    owner.provider_epub_view.close_find()
    app.show_home()
    from logisticsmobile.obsidian import open_vault
    vault = await open_vault(app, LocalFiles(root), 'Child', destination='home')
    await check('notes-library')
    await vault.open_note('Child/Note.md')
    await check('notes-article')
    app.show_settings()
    from logisticsmobile.documentation_ui import show_documentation
    wiki = root / 'Wiki'
    wiki.mkdir(exist_ok=True)
    page = wiki / 'docs.md'
    page.write_text('# Rotation guide\n\nRetain the current help page.')
    show_documentation(app, wiki, page)
    await check('documentation')
    return {'rotation_preserves_panels': True, 'rotation_samples': samples}
