"""Opt-in on-device comic layout check; uses an existing ordinary library item."""
import asyncio
import json
from pathlib import Path


async def run(app):
    from rubicon.objc import Block, objc_id
    from toga_iOS.images import nsdata_to_bytes
    from toga_iOS.libs import UIGraphicsImageRenderer
    output = Path(app.paths.cache) / 'logistics-comic-layout'
    output.mkdir(parents=True, exist_ok=True)
    report = {'samples': [], 'success': False}
    try:
        await asyncio.sleep(2)
        catalog = app.reader_manager().catalog
        records, _ = await asyncio.to_thread(catalog.library_store.items)
        record = next(item for item in records if item['kind'] == 'comic' and not item.get('protected'))
        await app.open_book(record['id'])
        owner = app.readers.active
        assert owner.book_reader is not None
        window = app.main_window._impl.native

        async def capture(name):
            await asyncio.sleep(1)
            canvas = owner.book_content.children[0]._impl
            rect = canvas.picture.convertRect(canvas.picture.bounds, toView=window)
            viewport = canvas.native.convertRect(canvas.native.bounds, toView=window)
            size, safe = window.bounds.size, window.safeAreaInsets
            expected = (safe.top + size.height - safe.bottom) / 2
            center = rect.origin.y + rect.size.height / 2
            sample = dict(name=name, fullscreen=owner.reader_immersive,
                window_height=float(size.height), top=float(rect.origin.y),
                height=float(rect.size.height), center=float(center), expected_center=float(expected),
                delta=float(center - expected), viewport_top=float(viewport.origin.y),
                viewport_height=float(viewport.size.height), zoom=float(canvas.native.zoomScale))
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

        owner.set_reading_mode(True)
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
        report['success'] = all(abs(item['delta']) < 2 for item in report['samples'] if item['fullscreen'])
    except Exception as error:
        report['error'] = str(error)
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2))
