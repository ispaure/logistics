"""Generated mixed folders for the native Local File Browser."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from io import BytesIO
import json
from pathlib import Path
import struct
from threading import Event
from time import monotonic
from unittest.mock import patch
from zipfile import ZipFile
import zlib

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION


def png(width, rgb):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', width, 17, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress((b'\0' + bytes(rgb) * width) * 17)) +
            chunk(b'IEND', b''))


def mixed_content():
    from features.notebooks.notebook import Notebook
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(95, 160)
    artwork = DecodedStreamObject()
    artwork.set_data(b'0.2 0.4 0.8 rg 10 10 75 140 re f')
    page[NameObject('/Contents')] = writer._add_object(artwork)
    pdf = BytesIO()
    writer.write(pdf)
    book = Notebook.new('Thumbnail fixture')
    book.page(0).add([[200, 200, .5], [1100, 1300, .5]], tool=18, color=6)
    comic = BytesIO()
    with ZipFile(comic, 'w') as archive:
        archive.writestr('page10.png', png(42, (0, 100, 22)))
        archive.writestr('page2.png', png(25, (0, 100, 222)))
    return {'001-image.png': png(21, (220, 40, 50)), '002-notebook.rmdoc': book.to_bytes(),
            '003-document.pdf': pdf.getvalue(), '004-comic.cbz': comic.getvalue()}


async def wait_for(predicate, message, *, timeout=12):
    deadline = monotonic() + timeout
    while not predicate():
        assert monotonic() < deadline, message() if callable(message) else message
        await asyncio.sleep(.025)


def preview_attached(browser, identity):
    box, placeholder = browser._tile_previews[identity]
    return box.children[0] is not placeholder and box.children[0].image is not None


def cached(browser, name):
    return next((data for (path, _), data in browser.icons.items() if path.name == name), b'')


async def expect_formats(browser, names, message):
    try:
        await wait_for(lambda: all(cached(browser, name) for name in names), message)
    except AssertionError as error:
        # Capture whether the failure is native viewport admission or decoding.
        source = browser.thumbnails
        rows = {entry.label: entry.payload for entry in browser.entries}
        missing = {}
        for name in names:
            if name in rows and not cached(browser, name):
                try:
                    data = await asyncio.to_thread(source._load, rows[name], (160, 160), lambda: False)
                    missing[name] = 'direct decode succeeded' if data else 'direct decode returned no image'
                except Exception as failure:
                    missing[name] = type(failure).__name__ + ': ' + str(failure)[:200]
        raise AssertionError(dict(message=message, missing=missing, visible=browser._previews_visible,
            visible_rows=list(browser._visible_rows()), tiles=[path.name for path in browser._tile_previews],
            jobs=len(browser._preview_jobs))) from error


async def assert_remote_placeholders(app, sample):
    """Mount previewable names in an already listed native Cloud browser."""
    browser = app.remote_browser
    rows = [entry.payload for entry in browser.folder_tree.entries.values() if entry.payload is not None]
    folder = sample['path'].rsplit('/', 1)[0]
    fixture = [dict(sample, name=name, path=f'{folder}/{name}') for name in mixed_content()]
    with patch.object(app.cloud_client, 'request', wraps=app.cloud_client.request) as request:
        try:
            browser.refresh_entries(fixture)
            await wait_for(lambda: len(browser.native_list.data) == len(fixture), 'Cloud rows were not mounted')
            await asyncio.sleep(.2)
            assert all(not row.thumbnail for row in browser.native_list.data)
            assert not browser.icons and not app.downloads.items()
            # iOS may refresh the ancestor listing as its navigation stack
            # mounts. Metadata listings do not read any remote file bytes.
            actions = [call.args[0] for call in request.call_args_list]
            assert set(actions) <= {'list'}, actions
        finally:
            browser.refresh_entries(rows)
    print('LOGISTICS_NATIVE_DETAIL={"remote_thumbnail_requests":0}', flush=True)


async def exercise_browser_thumbnails(app):
    from services.documents.locations import collection_path
    folder = collection_path(app.private_root) / 'p8-mixed-fixture'
    folder.mkdir()
    contents = mixed_content()
    for name, data in contents.items():
        (folder / name).write_bytes(data)
    for index in range(5, 165):
        if index % 5 == 0:
            (folder / f'{index:03}.txt').write_text('Placeholder')
        else:
            (folder / f'{index:03}.png').write_bytes(png(21 + index, (index, 20, 90)))
    (folder / 'subfolder').mkdir()
    location = ('Local files', folder.name)
    assert await app.show_files(location=location), app.file_status.value
    browser = app.file_browser
    source = browser.thumbnails
    gate = Event()
    calls = []
    original = type(source).load
    build_card = browser._tile_card
    build_tiles, mount_listing = browser._render_tiles, browser._mount_listing
    tile_build_seconds = tile_mount_seconds = card_seconds = 0.0
    cards_created = 0

    def slow(source, row, size, cancelled):
        if row['path'].startswith(folder.name + '/'):
            calls.append(Path(row['path']).name)
            # Only the test retires the hold. A wall-clock release can admit
            # more decodes while the runner is still scheduling the viewport.
            gate.wait()
        return original(source, row, size, cancelled)

    def timed_build_tiles():
        nonlocal tile_build_seconds
        started = monotonic()
        build_tiles()
        tile_build_seconds += monotonic() - started

    def timed_card(entry):
        nonlocal card_seconds, cards_created
        started = monotonic()
        card = build_card(entry)
        card_seconds += monotonic() - started
        cards_created += 1
        return card

    def timed_mount_listing(view):
        nonlocal tile_mount_seconds
        started = monotonic()
        mount_listing(view)
        if view is browser._tile_scroll and view.parent is browser.widget:
            tile_mount_seconds += monotonic() - started

    with patch.object(type(source), 'load', slow), \
            patch.object(browser, '_render_tiles', new=timed_build_tiles), \
            patch.object(browser, '_tile_card', new=timed_card), \
            patch.object(browser, '_mount_listing', new=timed_mount_listing):
        try:
            await wait_for(lambda: len(calls) == 2, ('workers', calls))
            assert len(browser._preview_jobs) == 2
            jobs = tuple(browser._preview_jobs.values())
            started = monotonic()
            browser.native_list.scroll_to_bottom()
            scrolled_at = monotonic()
            await wait_for(lambda: all(job.is_set() for job in jobs), 'Recycled rows kept thumbnail work',
                           timeout=2)
            cancelled_at = monotonic()
            first = browser._visible_rows()[0]
            assert first > 100, first
            anchor = browser._list_entries[first]
            nearby_image = next(entry for entry in browser._list_entries[first:] if entry.suffix == '.png')
            browser.view_switch.on_press()
            assert browser.mode == 'Tiles' and browser.location == location
            switched_at = monotonic()
            timing = dict(cancel_seconds=cancelled_at - started,
                          switch_seconds=switched_at - cancelled_at,
                          elapsed_seconds=switched_at - started,
                          scroll_call_seconds=scrolled_at - started,
                          cancel_after_scroll_seconds=cancelled_at - scrolled_at,
                          tile_build_seconds=tile_build_seconds,
                          tile_mount_seconds=tile_mount_seconds,
                          tile_card_seconds=card_seconds, tiles_constructed=cards_created,
                          decoder_starts=len(calls), elapsed_limit=2, decoder_limit=2)
            print('LOGISTICS_NATIVE_DETAIL=' + json.dumps(dict(thumbnail_view_switch=timing)), flush=True)
            assert timing['decoder_starts'] == 2, ('Decoder started while both slots were held', timing)
            assert timing['elapsed_seconds'] < 2, ('Scroll and mode switch exceeded two seconds', timing)
            await wait_for(lambda: browser.vertical_position > 0, 'Tile mode lost the scrolled viewport')
            gate.set()
            await wait_for(lambda: bool(cached(browser, nearby_image.label)),
                           f'Scrolled tile for {nearby_image.label} has no preview')
            from commonUtils.formats.image_headers import image_header
            image = image_header(cached(browser, nearby_image.label), max_bytes=1024 * 1024)
            width, height = browser._tile_thumbnail_size()
            source_width = 21 + int(Path(nearby_image.label).stem)
            assert (image.width, image.height) == (width, max(1, width * 17 // source_width))
            assert width > 160 and height > 160
            assert not cached(browser, '001-image.png'), 'Recycled row published a thumbnail'
            browser.view_switch.on_press()
            await wait_for(lambda: bool(browser._visible_rows()) and browser._visible_rows()[0] > 100,
                           'Row mode lost the scrolled viewport')
            actual = browser._list_entries[browser._visible_rows()[0]]
            assert actual.identity == anchor.identity, (anchor.label, actual.label)
            app.show_home()
            await wait_for(lambda: not browser._previews_visible, 'Hidden browser kept scheduling work')
            await app.show_files()
            assert app.file_browser is browser and browser.location == location
            await wait_for(lambda: browser._previews_visible, 'Returned browser did not resume previews')

            # Android has a pending native layout when the retained route is
            # remounted. A scroll requested before it settles can be superseded.
            await wait_for(lambda: bool(browser._visible_rows()) and browser._visible_rows()[0] == first,
                           'Returned browser lost the scrolled row')
            for _ in range(5):
                browser.native_list.scroll_to_row(0)
                await asyncio.sleep(.15)
                if 0 in browser._visible_rows():
                    break
            assert 0 in browser._visible_rows(), list(browser._visible_rows())
            await expect_formats(browser, contents, 'The four preview formats did not all render')
            assert image_header(cached(browser, '001-image.png'), max_bytes=1024 * 1024).width == 160
            assert image_header(cached(browser, '004-comic.cbz'), max_bytes=1024 * 1024).height == 108
            image_entry = next(entry for entry in browser.entries if entry.label == '001-image.png')
            await browser.select(image_entry)
            browser.view_switch.on_press()
            await wait_for(lambda: preview_attached(browser, image_entry.identity),
                           'The tile did not load a larger preview')
            tile = image_header(cached(browser, '001-image.png'), max_bytes=1024 * 1024)
            assert tile.width > 160 and tile.height > 160
            assert browser.selected == image_entry.identity and browser.buttons[image_entry.identity].text == image_entry.label
            assert calls.count('001-image.png') <= 2, calls

            old = cached(browser, '001-image.png')
            (folder / '001-image.png').write_bytes(png(21, (10, 220, 40)))
            browser.refresh_entries(app.file_provider.list(folder.name))
            await wait_for(lambda: cached(browser, '001-image.png') not in (b'', old),
                           'Changed content reused an old thumbnail')
            assert all(item != old for item in browser.icons.values())
        finally:
            gate.set()
    browser.show_list()
    assert await app.browser_file_location(('Local files', '')), app.file_status.value
    print('LOGISTICS_NATIVE_DETAIL=' + json.dumps(dict(browser_thumbnails='passed',
          mixed_items=165, peak_decoders=2, formats=list(contents))), flush=True)


async def exercise_locked_thumbnails(app, provider, label):
    """Keep one decode in flight across the real credential lock."""
    from shutil import rmtree
    folder = 'p8-thumbnail-lock'
    provider.mkdir(folder)
    physical = provider._physical(folder, directory=True)
    contents = mixed_content()
    for name, data in contents.items():
        provider.create_file(folder + '/' + name, BytesIO(data))
    assert await app.show_files(location=(label, folder)), app.file_status.value
    browser = app.file_browser
    gate, started = Event(), Event()
    original = type(browser.thumbnails).load

    def delayed(source, row, size, cancelled):
        data = original(source, row, size, cancelled)
        if row['path'] == folder + '/080-delayed.png' and data:
            started.set()
            gate.wait(8)
        return data

    def state():
        return dict(visible=browser._previews_visible, mode=browser.mode,
                    active=app.active_host, paused=app.screen_privacy._folder_work_paused,
                    private=browser.thumbnails.private, valid=browser.thumbnails.can_publish(),
                    entries=[entry.label for entry in browser.entries],
                    tiles=[path.name for path in browser._tile_previews],
                    cached=[name for name in contents if cached(browser, name)],
                    active_workers=len(browser._preview_jobs))

    try:
        browser.show_tiles()
        await expect_formats(browser, contents, 'Unlocked LocalCrypt thumbnails did not render')
        with patch.object(type(browser.thumbnails), 'load', delayed):
            await asyncio.to_thread(provider.create_file, folder + '/080-delayed.png', BytesIO(png(18, (70, 20, 220))))
            browser.refresh_entries(await asyncio.to_thread(provider.list, folder))
            await wait_for(started.is_set, lambda: ('Private decode did not start', state()))
            source = browser.thumbnails
            prior_tiles = [box.children[0] for box, placeholder in browser._tile_previews.values()
                           if box.children[0] is not placeholder]
            await app.lock_cloud()
            # Release simulated late plaintext only after the catalog has been cleared.
            gate.set()
            await wait_for(lambda: not browser._preview_jobs, 'A revoked decoder did not retire')
            assert browser.closed and not browser.icons and not browser.work.decoded
            assert not browser._tile_previews and not len(browser.native_list.data)
            assert all(image.image is None for image in prior_tiles)
            assert not source.can_publish()
            print('LOGISTICS_NATIVE_DETAIL=' + json.dumps(dict(localcrypt_thumbnails='passed',
                  late_result_discarded=True)), flush=True)
    finally:
        gate.set()
        rmtree(physical)
