"""Real native page-layer presence, plus mobile high-contrast suppression."""


async def exercise(app, name):
    if not getattr(app, 'page_turns', False):
        return
    if name in ('epub', 'comic'):
        owner = app.readers.active
        move, content = owner.move_book_page, owner.book_content
    elif name == 'Page-pdf' or name.endswith(('-epub', '-cbz')):
        owner = app.private_sessions.active
        move, content = owner.move_private_page, owner.crypt_content
    else:
        return
    from mobile import page_animation
    original = page_animation.begin_page_slide
    preference = app.preferences.values['android_eink']
    rows = []
    stage, outgoing = 'single', None
    comic = name == 'comic' or name.endswith('-cbz')
    previous_layout = app.preferences.values['comic_layout']
    def displayed_image():
        def find(widget):
            if getattr(widget, 'image', None) is not None and hasattr(widget._impl, 'picture'):
                return widget._impl.picture.image
            for child in widget.children:
                result = find(child)
                if result is not None:
                    return result
        return find(content)
    def begin(surface, direction, preferences):
        try:
            if comic and surface is content and direction and outgoing is not None:
                assert displayed_image() == outgoing, 'Comic pixels changed before transition capture'
            original(surface, direction, preferences)
        except Exception as error:
            rows.append(dict(panel=name, direction=direction, error=repr(error)))
            raise
        if surface is content and direction and outgoing is not None:
            from ctypes import CDLL, c_bool
            reduced = CDLL(None).UIAccessibilityIsReduceMotionEnabled
            reduced.restype = c_bool
            import time
            started_at = time.time()
            state = getattr(surface._impl, '_ios_page_slide', None)
            active = state is not None and state.snapshot is not None
            high_contrast = preferences.get('android_eink') == 'true'
            rows.append(dict(panel=name, layout=stage, direction=direction, high_contrast=high_contrast, started_at=started_at,
                             native_slide=active, outgoing_pixels_preserved=bool(comic), reduced_motion=bool(reduced())))
    async def checked_move(target=None, *, swipe=None):
        import asyncio
        nonlocal outgoing
        await asyncio.sleep(.3)
        outgoing = displayed_image() if comic else object()
        before = len(rows)
        if swipe is None:
            await move(target)
        else:
            gesture = owner.swipe_book_page if name == 'comic' else owner.swipe_crypt_page
            gesture(swipe)
            await owner._comic_swipe_task
        assert len(rows) == before + 1, (name, stage, target, swipe, rows, str(getattr(owner, 'book_status', None)), getattr(owner, 'book_busy', None))
        if comic:
            assert displayed_image() != outgoing, 'The destination comic bitmap did not change'
        outgoing = None
    page_animation.begin_page_slide = begin
    try:
        if comic:
            app.preferences.values['comic_layout'] = 'single'
            await move(0)
        for contrast in (False, True):
            app.preferences.values['android_eink'] = 'true' if contrast else 'false'
            await checked_move(1)
            await checked_move(0)
        if comic:
            stage = 'double'
            app.preferences.values['comic_layout'] = 'double'
            await move(0)
            for contrast in (False, True):
                app.preferences.values['android_eink'] = 'true' if contrast else 'false'
                await checked_move(1)
                await checked_move(0)
            stage = 'split'
            app.preferences.values['comic_layout'] = 'single'
            await move(4)
            nav = owner.comic_navigation if name == 'comic' else owner.crypt_reader.comic_navigation
            assert nav.split, (name, 'Wide fixture must exercise a reused crop canvas')
            for contrast in (False, True):
                app.preferences.values['android_eink'] = 'true' if contrast else 'false'
                await checked_move(swipe=1)
                await checked_move(swipe=-1)
            await move(0)
        expected = 12 if comic else 4
        assert len(rows) == expected and all('error' not in row and
            row['native_slide'] == (not row['high_contrast'] and not row['reduced_motion']) for row in rows), (name, rows)
        app.report.setdefault('page_motion_checks', []).extend(rows)
    finally:
        page_animation.begin_page_slide = original
        app.preferences.values['android_eink'] = preference
        app.preferences.values['comic_layout'] = previous_layout
    if name == 'epub' or name.endswith('-epub'):
        view = owner.epub_view if name == 'epub' else owner.provider_epub_view.webview
        await web_motion(app, name, view)


def expand_epub(path):
    from io import BytesIO
    from zipfile import ZipFile
    with ZipFile(path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    members['one.xhtml'] = ('<html><body><h1>Native EPUB first</h1>' +
        '<p>A long synthetic passage for page-turn motion and retained anchors.</p>' * 400 + '</body></html>').encode()
    output = BytesIO()
    with ZipFile(output, 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    path.write_bytes(output.getvalue())


async def web_motion(app, name, view):
    import asyncio
    import json
    for _ in range(100):
        state = await view.evaluate_javascript('JSON.stringify(window.reader && reader.pagination())')
        if state and json.loads(state).get('count', 0) > 1:
            break
        await asyncio.sleep(.1)
    else:
        raise AssertionError('Native paginated EPUB did not become ready')
    from mobile.page_animation import sync_preferences
    preference = app.preferences.values['android_eink']
    app.preferences.values['android_eink'] = 'false'
    sync_preferences(app)
    normal = json.loads(await view.evaluate_javascript("""
        (()=>{reader.seek(0);reader.turn(1);return JSON.stringify({
          ...reader.pagination(),animations:document.getAnimations().length});})()
    """))
    assert normal['index'] == 1 and normal['anchor'] > 0 and normal['animations'] > 0, normal
    app.preferences.values['android_eink'] = 'true'
    sync_preferences(app)
    contrast = json.loads(await view.evaluate_javascript("""
        (()=>{reader.turn(-1);const result={...reader.pagination(),animations:document.getAnimations().length};
          reader.seek(0);return JSON.stringify(result);})()
    """))
    app.preferences.values['android_eink'] = preference
    sync_preferences(app)
    assert contrast['index'] == 0 and contrast['animations'] == 0, contrast
    app.report.setdefault('web_page_motion_checks', []).append(dict(panel=name, normal=normal, high_contrast=contrast))


def expand_comic(path):
    import struct
    import zlib
    from zipfile import ZipFile
    def png(width, height, left, right):
        def chunk(kind, data):
            return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
        row = bytes(left) * (width // 2) + bytes(right) * (width - width // 2)
        raw = (b'\x00' + row) * height
        return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) +
                chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
    colors = [(255,0,0,255), (0,0,255,255), (0,180,0,255), (255,200,0,255)]
    with ZipFile(path, 'w') as archive:
        for index, color in enumerate(colors):
            archive.writestr(str(index) + '.png', png(120, 180, color, color))
        archive.writestr('4.png', png(240, 120, colors[0], colors[1]))
