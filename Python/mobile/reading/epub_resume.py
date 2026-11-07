"""Restore the visible EPUB after a Settings visit or a released page."""
import asyncio
import json
import logging

from features.books.mobile.typography import DEFAULTS

APPEARANCE_KEYS = (*DEFAULTS, 'epub_font_size', 'reading_margin', 'reading_theme')


def appearance(values):
    return tuple(values[key] for key in APPEARANCE_KEYS)


def bridge_for(owner, provider):
    view = (getattr(getattr(owner, 'provider_epub_view', None), 'webview', None)
            if provider else getattr(owner, 'epub_view', None))
    return getattr(view, '_chapter_bridge', None)


def resume_visible_epub(app):
    if not app.active_host or app.screen_privacy.inactive or any(gate.locked for gate in app.screen_privacy.gates()):
        return
    key = app.visible_reader()
    if key is None:
        return
    for name in ('readers', 'private_sessions'):
        manager = getattr(app, name, None)
        owner = getattr(manager, 'active', None)
        if getattr(getattr(owner, 'session', None), 'id', None) == key:
            break
    else:
        return

    provider = name == 'private_sessions'
    if provider:
        reader = owner.crypt_reader
        if reader is None or reader.book is None or not manager.available(key):
            return
        if getattr(owner, 'page_suspended', False):
            owner.resume_suspended_page()
            return
    else:
        if owner.session.kind != 'epub':
            return
        if owner.book_reader is None:
            owner.resume_suspended_page()
            return

    bridge = bridge_for(owner, provider)
    changed = owner._epub_appearance != appearance(app.preferences.values)
    pending = getattr(owner, '_epub_return_pending', False)
    task = getattr(owner, '_epub_resume_task', None)
    if (not (changed or pending) or (task is not None and not task.done())):
        return

    def current():
        return (app.active_host and not app.screen_privacy.inactive
                and not any(gate.locked for gate in app.screen_privacy.gates())
                and manager.active is owner and app.visible_reader() == key
                and (not provider or manager.available(key))
                and bridge_for(owner, provider) is bridge)

    async def restore():
        idle = owner.operation_idle if provider else owner._book_idle
        await idle.wait()
        if not current():
            return
        reload_page = owner._epub_appearance != appearance(app.preferences.values)
        if not reload_page and pending and bridge is not None and bridge.native_pagination:
            try:
                result = await asyncio.wait_for(bridge.view.evaluate_javascript(
                    '!!(window.reader && window.reader.root === ' + json.dumps(bridge.root)
                    + ' && !window.reader.disposed && window.reader.resume())'), timeout=1)
                reload_page = not result
            except Exception as error:
                logging.getLogger(__name__).debug('EPUB layout did not resume: %s', error)
                reload_page = True
        if not current():
            return
        owner._epub_return_pending = False
        if bridge is not None:
            bridge.input_suspended = False
        if reload_page:
            if provider:
                panel = owner.provider_epub_view
                owner._provider_epub_target = panel.offset
                await owner.move_private_page(panel.index)
            else:
                owner._epub_target = owner.epub_offset
                await owner.move_book_page(owner.book_record['position'])

    owner._epub_resume_task = app.loop.create_task(restore())
