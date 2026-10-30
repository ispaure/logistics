"""Opt-in volume paging resolves the visible document for every physical press."""


def target(app):
    from .routes import contains
    privacy = getattr(app, 'screen_privacy', None)
    if (not app.active_host or getattr(app, '_reset_scheduled', False)
            or (privacy is not None and (privacy.inactive or privacy.resume_locked))):
        return None
    key = app.visible_reader()
    if key is None or app.reader_tool_back(app.body) is not None:
        return None
    for name, surface, busy, previous, following in (
            ('readers', 'library_view', 'book_busy', 'previous_book_page', 'next_book_page'),
            ('private_sessions', 'crypt_view', 'cloud_busy', 'previous_private_page', 'next_private_page')):
        manager = getattr(app, name, None)
        owner = getattr(manager, 'controllers', {}).get(key)
        if owner is None or not contains(app.body, getattr(owner, surface, None)):
            continue
        kind = owner.session.kind
        if kind not in {'epub', 'comic'} or app.preferences.values.get(kind + '_volume_pages') != 'true':
            return None
        return owner, busy, previous, following
    return None


class VolumePages:
    def __init__(self, app):
        from java import dynamic_proxy, jclass
        bridge = jclass('io.github.ispaure.logisticsmobile.ReaderVolumeKeys')
        owner = self

        class Listener(dynamic_proxy(bridge.Listener)):
            def onVolumeKey(self, direction):
                return owner.press(direction)

        self.app = app
        self.task = None
        self.listener = Listener()
        self.native = bridge(app.native_host.adapter.impl._native_activity, self.listener)

    def press(self, direction):
        selected = target(self.app)
        if selected is None:
            return False
        owner, busy, previous, following = selected
        if getattr(owner, busy, False) or (self.task is not None and not self.task.done()):
            return True

        async def turn():
            # Routes/privacy can change before the event loop runs this task.
            if target(self.app) == selected and not getattr(owner, busy, False):
                await getattr(owner, following if direction > 0 else previous)()

        self.task = self.app.loop.create_task(turn())
        return True

    def dispose(self):
        self.native.dispose()
        if self.task is not None and not self.task.done():
            self.task.cancel()
        self.listener = None
