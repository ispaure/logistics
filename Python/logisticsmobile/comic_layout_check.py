"""Opt-in on-device comic layout check; uses an existing ordinary library item."""
import asyncio
import json
from pathlib import Path


async def fixture_reader(app, output, *, pages=1, right_to_left=False):
    """A cache-only comic and transient session; never an ordinary library import."""
    import struct
    import zlib
    from zipfile import ZipFile
    from commonUtils.runtime.document_access import LocalDocuments
    from .library import LibraryStore
    from .reader_sessions import ReaderController
    from .reader_ui import ReaderUI
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    width, height = 768, 1024
    pixels = (b'\x00' + b'\xe0\xe8\xf0\xff' * width) * height
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))
    archive = output / 'layout-fixture.cbz'
    with ZipFile(archive, 'w') as stream:
        for index in range(pages):
            stream.writestr(f'page{index:03}.png', png)
        if right_to_left:
            stream.writestr('ComicInfo.xml', '<ComicInfo><Manga>YesAndRightToLeft</Manga></ComicInfo>')
    store = LibraryStore(output / 'fixture-library')
    record = store.import_book(LocalDocuments(), archive)
    session = app.workspace.open('library', record['id'], 'comic', 'Layout check', transient=True)
    manager = app.reader_manager()
    owner = ReaderController(manager, session)
    manager.controllers[session.id] = owner
    owner.show_library()
    owner.library_store = store
    # Bypass the normal controller's persistent-import classification.
    await ReaderUI.open_book(owner, record['id'])
    return owner


async def run(app):
    from rubicon.objc import Block, objc_id
    from toga_iOS.images import nsdata_to_bytes
    from toga_iOS.libs import UIGraphicsImageRenderer
    output = Path(app.paths.cache) / 'logistics-comic-layout'
    output.mkdir(parents=True, exist_ok=True)
    report = {'samples': [], 'success': False}
    fixture = None
    previous_selection = app.workspace.active
    previous_routes = len(app.routes.screens['documents'])
    try:
        await asyncio.sleep(2)
        catalog = app.reader_manager().catalog
        import os
        if os.environ.get('LOGISTICS_COMIC_LAYOUT_FIXTURE') == '1':
            owner = fixture = await fixture_reader(app, output)
        else:
            records, _ = await asyncio.to_thread(catalog.library_store.items)
            record = next((item for item in records if item['kind'] == 'comic' and not item.get('protected')), None)
            if record is None:
                raise ValueError('No ordinary imported comic is available for this diagnostic.')
            await app.open_book(record['id'])
            owner = app.readers.active
        assert owner.book_reader is not None
        window = app.main_window._impl.native

        async def capture(name):
            await asyncio.sleep(1)
            page = owner.book_content.children[0]
            canvas = getattr(page, 'canvas', page)._impl
            rect = canvas.picture.convertRect(canvas.picture.bounds, toView=window)
            viewport = canvas.native.convertRect(canvas.native.bounds, toView=window)
            size, safe = window.bounds.size, window.safeAreaInsets
            # Immersive image canvases deliberately extend under safe areas;
            # center within the actual viewport, not the removed chrome's inset.
            expected = viewport.origin.y + viewport.size.height / 2
            center = rect.origin.y + rect.size.height / 2
            sample = dict(name=name, fullscreen=owner.reader_immersive,
                window_height=float(size.height), top=float(rect.origin.y),
                height=float(rect.size.height), center=float(center), expected_center=float(expected),
                delta=float(center - expected), viewport_top=float(viewport.origin.y),
                viewport_height=float(viewport.size.height), zoom=float(canvas.native.zoomScale))
            sample.update(viewport_left=float(viewport.origin.x), viewport_width=float(viewport.size.width),
                expected_left=float(safe.left), expected_width=float(size.width - safe.left - safe.right))
            if not owner.reader_immersive:
                adapter = app.native_host.adapter
                sample['no_browser_menu'] = not hasattr(owner.library_view, '_workspace_menu_button')
                bar = adapter.controller.tabBar
                tab_rect = bar.convertRect(bar.bounds, toView=window)
                status = owner.book_status._impl.native
                status_rect = status.convertRect(status.bounds, toView=window)
                sample['status_bottom'] = float(status_rect.origin.y + status_rect.size.height)
                sample['tab_top'] = float(tab_rect.origin.y)
                sample['status_accessible'] = bar.isHidden() or sample['status_bottom'] <= sample['tab_top'] + 1
            ancestors = []
            node = owner.book_content.children[0]
            while node is not None:
                bounds = node._impl.native.bounds.size
                ancestors.append(dict(type=type(node).__name__, flex=node.style.flex,
                    width=float(bounds.width), height=float(bounds.height)))
                node = node.parent
            container = canvas.container
            sample['ancestors'] = ancestors
            sample['container'] = dict(height=float(container.native.bounds.size.height),
                layout_height=float(container.layout_native.bounds.size.height),
                top=float(container.top_inset), bottom=float(container.bottom_inset))
            report['samples'].append(sample)
            renderer = UIGraphicsImageRenderer.alloc().initWithSize(size)
            def draw(context):
                window.drawViewHierarchyInRect(window.bounds, afterScreenUpdates=True)
            (output / (name + '.png')).write_bytes(nsdata_to_bytes(renderer.PNGDataWithActions(Block(draw, None, objc_id))))
            (output / 'report.json').write_text(json.dumps(report, indent=2))

        await capture('fullscreen-initial')
        for index in range(3):
            owner.book_content.children[0].toggle_controls()
            await capture(f'controls-{index + 1}')
            owner.book_content.children[0].toggle_controls()
            await capture(f'fullscreen-{index + 1}')
            app.show_settings()
            await asyncio.sleep(.3)
            owner.show_library()
            await capture(f'reopened-{index + 1}')
        report['success'] = all(
            (abs(item['delta']) < 2
             and abs(item['viewport_width'] - item['expected_width']) < 2
             and abs(item['viewport_left'] - item['expected_left']) < 2
             and abs(item['viewport_top']) < 2
             and abs(item['viewport_height'] - item['window_height']) < 2) if item['fullscreen']
            else item['no_browser_menu'] and item['status_accessible'] for item in report['samples'])
    except Exception as error:
        report['error'] = str(error)
    finally:
        if fixture is not None:
            fixture.release_book_reader()
            app.readers.controllers.pop(fixture.session.id, None)
            app.workspace.close(fixture.session.id, guard=lambda session: True)
            if previous_selection in app.workspace.sessions:
                app.workspace.activate(previous_selection)
            app.readers.active = app.readers.catalog
            app.routes.trim('documents', previous_routes)
            app.show_home()
            app.save_workspace()
        (output / 'report.json').write_text(json.dumps(report, indent=2))
