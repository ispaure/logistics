"""One explicit exit policy for mobile document owners and storage sources."""


def session_route(route):
    return route == 'editor' or (route or '').startswith(('private:', 'reader:', 'file-loading:'))


def scroll_position(widget):
    if widget is None:
        return None
    native = getattr(widget._impl, 'native', None)
    backend = getattr(widget, 'backend_name', type(widget._impl).__module__)
    if backend.startswith('toga_android.'):
        return max(0, int(native.getScrollX())), max(0, int(native.getScrollY()))
    if backend.startswith('toga_iOS.'):
        scroll = native.scrollView if hasattr(native, 'scrollView') else native
        point = scroll.contentOffset
        return max(0, int(point.x)), max(0, int(point.y))
    return None


def restore_scroll(widget, position):
    if widget is None or position is None:
        return
    native = getattr(widget._impl, 'native', None)
    backend = getattr(widget, 'backend_name', type(widget._impl).__module__)
    if backend.startswith('toga_android.'):
        native.scrollTo(*position)
    elif backend.startswith('toga_iOS.'):
        from rubicon.objc import CGPoint
        scroll = native.scrollView if hasattr(native, 'scrollView') else native
        scroll.setContentOffset(CGPoint(*position), animated=False)


async def restore_drawn_scroll(widget, position, valid):
    """Font/viewport reflow must finish before restoring native scroll offsets."""
    import asyncio
    from .draw_ready import wait_for_draw
    binding = getattr(widget, '_font_binding', None)
    pending = getattr(binding, 'task', None)
    if pending is not None and not pending.done():
        try:
            await asyncio.wait_for(asyncio.shield(pending), timeout=.5)
        except asyncio.TimeoutError:
            pass
    if valid():
        await wait_for_draw(widget)
    if valid():
        restore_scroll(widget, position)


def restore_loaded_scroll(widget, position, valid):
    """Wait for actual WebView content, preserving its search/load handler."""
    if position is None:
        return
    previous = widget.on_webview_load
    restored = False
    async def loaded(view, **kwargs):
        nonlocal restored
        import inspect
        result = previous(**kwargs) if previous is not None else None
        if inspect.isawaitable(result):
            await result
        if not restored and valid():
            restored = True
            await restore_drawn_scroll(view, position, valid)
        if getattr(view.on_webview_load, '_raw', None) is loaded:
            view.on_webview_load = getattr(previous, '_raw', previous)
    widget.on_webview_load = loaded


class ReaderLifecycle:
    def bind_reader_exit(self, view, route, destination):
        """Main documents use Close; secondary screens keep route Back."""
        key = None
        if route and route.startswith(('private:', 'reader:')) and route.count(':') == 1:
            key = route.split(':')[1]
        elif route in ('editor', 'preview'):
            session = getattr(self.editor_view, 'session', None)
            key = session.id if session is not None else None
        if key is None or key not in self.workspace.sessions:
            return
        returns = self.__dict__.setdefault('_reader_returns', {})
        presentations = self.routes.screens[destination]
        if destination == 'documents':
            presentations = [*presentations, *self.adaptive.detail_routes]
        presented = any(getattr(child, '_reader_session_id', None) == key
                        for _, panel, _ in presentations for child in panel.children)
        if (key not in returns or returns[key][0] != destination
                or not presented
                or getattr(self, '_file_loading', None) is not None):
            origin = self.native_host.state.destination
            screens = self.routes.screens[origin]
            count = len(screens)
            drawer = self.adaptive.menu_open.get(origin, False)
            while count and (screens[count - 1][0].startswith('file-loading:')
                             or (not drawer and session_route(screens[count - 1][0]))):
                count -= 1
            returns[key] = origin, screens[count - 1][0] if count else None, drawer
        view._reader_session_id = key
        if not hasattr(view, '_reader_close_button'):
            from .control_icons import icon_button
            button = icon_button('close', 'Close document',
                on_press=lambda widget=None, **kw: self.request_reader_close(key))
            view._reader_close_button = button
            toolbar = getattr(view, '_native_reader_toolbar', None)
            if toolbar is not None:
                toolbar.insert(0, button)

    def visible_reader(self):
        def keys(view):
            key = getattr(view, '_reader_session_id', None)
            if key in self.workspace.sessions:
                yield key
            for child in view.children:
                yield from keys(child)
        visible = list(keys(self.body))
        return self.workspace.active if self.workspace.active in visible else next(iter(visible), None)

    def request_reader_close(self, key):
        self.__dict__.setdefault('_reader_closing', set()).add(key)
        readers = getattr(self, 'readers', None)
        owner = readers.controllers.get(key) if readers is not None else None
        pending = getattr(owner, '_epub_location_task', None)
        if pending is not None and pending.done():
            pending = None
        if pending is not None:
            owner.request_position_flush()
        else:
            private = self.provider_sessions().controllers.get(key)
            if private is not None and private.operation_busy:
                owner = private
                if getattr(owner, '_exit_task', None) is not None:
                    return True
                pending = private.operation_idle.wait()
        if pending is not None:
            if getattr(owner, '_exit_task', None) is None:
                async def finish():
                    try:
                        await pending
                        if key in self.workspace.sessions:
                            self.request_close_session(key)
                    finally:
                        owner._exit_task = None
                owner._exit_task = self.loop.create_task(finish())
            return True
        return self.request_close_session(key)

    def keep_reader_editing(self, key):
        self.__dict__.setdefault('_reader_closing', set()).discard(key)
        owner = self.provider_sessions().controllers.get(key)
        if owner is not None:
            owner.resume_crypt()
        else:
            readers = getattr(self, 'readers', None)
            book = readers.controllers.get(key) if readers is not None else None
            if book is not None:
                book.show_view(book.book_metadata_view, reader_route='metadata', title='Edit metadata')
            else:
                self.cancel_close_session(key)

    @staticmethod
    def book_edits_dirty(owner):
        return any(field.value != owner.book_metadata_initial.get(name, '')
                   for name, field in getattr(owner, 'book_metadata_fields', {}).items())

    def request_book_close(self, owner):
        import toga
        from toga.style import Pack
        from toga.style.pack import COLUMN
        key = owner.session.id
        status = toga.Label('')
        async def save(widget=None, **kwargs):
            await owner.save_book_metadata()
            if self.book_edits_dirty(owner):
                status.text = owner.book_metadata_status.text
            else:
                self.close_session(key)
        box = toga.Box(children=[toga.Label('Save metadata changes before closing?'),
            toga.Button('Save and close', on_press=save),
            toga.Button('Discard and close', on_press=lambda widget, **kw: self.close_session(key, choice='discard')),
            toga.Button('Keep editing', on_press=lambda widget, **kw: self.keep_reader_editing(key)), status],
            style=Pack(direction=COLUMN, margin=16, flex=1))
        self.show_view(box, route='close:' + key, title='Close document')

    def reader_closed(self, key):
        returns = self.__dict__.setdefault('_reader_returns', {})
        target = returns.pop(key, None)
        closing = self.__dict__.setdefault('_reader_closing', set())
        leaving = key in closing
        closing.discard(key)
        if not leaving or target is None:
            self.show_documents_hub()
            return
        destination, route, drawer = target
        # Retire every presentation of this closed session, including a close
        # prompt or a retained reader in another destination's stack.
        for current, screens in self.routes.screens.items():
            index = next((i for i, (name, panel, _) in enumerate(screens)
                          if name in ('private:' + key, 'reader:' + key, 'close:' + key,
                                      'private-close:' + key)
                          or any(getattr(child, '_reader_session_id', None) == key for child in panel.children)), None)
            if index is not None:
                self.routes.trim(current, index)
        details = self.adaptive.detail_routes
        index = next((i for i, (_, panel, _) in enumerate(details)
                      if any(getattr(child, '_reader_session_id', None) == key for child in panel.children)), None)
        if index is not None:
            self.adaptive.trim_details(index)
        screens = self.routes.screens[destination]
        count = next((i + 1 for i, screen in enumerate(screens) if screen[0] == route), 0)
        self.routes.trim(destination, count)
        if destination == 'documents' and self.adaptive.split is not None:
            self.adaptive.show_list()
        # This restores an existing route, not a second tap on Documents (which
        # intentionally collapses its stack to the overview).
        self.native_host.activate(destination)
        self.routes.render(destination)
        self.routes.folders.restore(destination)
        if drawer:
            self.adaptive.menu_open[destination] = True
            self.adaptive.render(preserve_drawer=True)
        if route is not None:
            self.loop.call_soon(self.routes.folders.restore_viewport, destination, route)
