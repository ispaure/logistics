"""Actual native image zoom, compact reading and sanitized appearance content."""
import asyncio


async def exercise_reader(app, passed):
    owner = app.reader_manager().active
    view = app.book_content.children[0]
    view.set_zoom(2)
    await asyncio.sleep(.2)
    assert 1.9 <= view.zoom_scale <= 2.1, view.zoom_scale
    view.fit_page()
    assert view.zoom_scale == 1
    owner.toggle_reading_mode()
    assert owner.reader_immersive and len(owner.library_view.children) == 2
    owner.toggle_reading_mode()
    assert not owner.reader_immersive
    previous = app.book_record['position']
    view.page(-1)
    await asyncio.sleep(.4)
    assert app.book_record['position'] == previous - 1
    app.book_content.children[0].page(1)
    await asyncio.sleep(.4)
    assert app.book_record['position'] == previous
    owner.show_reader_appearance()
    owner.reader_margin.value, owner.reader_theme.value = '24', 'dark'
    await owner.apply_reader_appearance()
    assert app.preferences.values['reading_margin'] == '24'
    assert app.book_record['position'] == previous
    owner.show_reader_tools()
    assert owner.bookmark_selector in owner.reader_tools_view.content.children
    owner.show_library()
    passed.append('native_reader_presentation')
