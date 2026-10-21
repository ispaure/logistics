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
    from logisticsmobile import page_animation
    original = page_animation.begin_page_slide
    preference = app.preferences.values['android_eink']
    rows = []
    def begin(surface, direction, preferences):
        try:
            original(surface, direction, preferences)
        except Exception as error:
            rows.append(dict(panel=name, direction=direction, error=repr(error)))
            raise
        if surface is content and direction:
            from rubicon.objc import ObjCClass
            from ctypes import CDLL, c_bool
            reduced = CDLL(None).UIAccessibilityIsReduceMotionEnabled
            reduced.restype = c_bool
            ObjCClass('CATransaction').flush()
            active = surface._impl.native.layer.animationForKey('transition') is not None
            high_contrast = preferences.get('android_eink') == 'true'
            rows.append(dict(panel=name, direction=direction, high_contrast=high_contrast, native_slide=active, backend=type(surface._impl).__module__, reduced_motion=bool(reduced())))
    page_animation.begin_page_slide = begin
    try:
        for contrast in (False, True):
            app.preferences.values['android_eink'] = 'true' if contrast else 'false'
            await move(1)
            await move(0)
        assert len(rows) == 4 and all('error' not in row and row['native_slide'] != row['high_contrast'] for row in rows), (name, rows)
        app.report.setdefault('page_motion_checks', []).extend(rows)
    finally:
        page_animation.begin_page_slide = original
        app.preferences.values['android_eink'] = preference
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
    normal = json.loads(await view.evaluate_javascript("""
        (()=>{reader.seek(0);reader.turn(1);return JSON.stringify({
          ...reader.pagination(),animations:document.getAnimations().length});})()
    """))
    assert normal['index'] == 1 and normal['anchor'] > 0 and normal['animations'] > 0, normal
    contrast = json.loads(await view.evaluate_javascript("""
        (()=>{const s=document.createElement('style');s.id='logistics-eink';document.head.appendChild(s);
          reader.turn(-1);const result={...reader.pagination(),animations:document.getAnimations().length};
          s.remove();reader.seek(0);return JSON.stringify(result);})()
    """))
    assert contrast['index'] == 0 and contrast['animations'] == 0, contrast
    app.report.setdefault('web_page_motion_checks', []).append(dict(panel=name, normal=normal, high_contrast=contrast))
