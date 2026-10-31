"""One explicit exit policy for mobile document owners and storage sources."""


def session_route(route):
    return route == 'editor' or (route or '').startswith(('private:', 'reader:', 'notebook:', 'file-loading:'))


def document_route(route):
    """Own the screen without changing a nested editor's return destination."""
    return session_route(route) or (route or '').startswith('notes-library:')


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
    from commonUtils.ui.native.draw_ready import wait_for_draw
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
        if route and route.startswith(('private:', 'reader:', 'notebook:', 'notes-library:')) and route.count(':') == 1:
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
                on_press=lambda widget=None, **kw: self.reader_exit(view, key))
            view._reader_close_button = button
            toolbar = getattr(view, '_native_reader_toolbar', None)
            if toolbar is not None:
                toolbar.insert(0, button)

    def reader_tool_back(self, view):
        """Return the innermost tool's dismiss action, without closing its owner."""
        from .routes import contains
        for owner in self.text_views.values():
            if contains(view, owner.search.box):
                return owner.toggle_search
        readers = getattr(self, 'readers', None)
        for owner in getattr(readers, 'controllers', {}).values():
            sidebar = getattr(owner, 'chapter_sidebar', None)
            if (contains(view, getattr(owner, 'library_view', None)) and sidebar is not None
                    and not sidebar.expanded and sidebar.sidebar_open):
                return sidebar.show_detail
        private = getattr(self, 'private_sessions', None)
        for owner in getattr(private, 'controllers', {}).values():
            epub = getattr(owner, 'provider_epub_view', None)
            if epub is not None:
                if contains(view, getattr(epub, 'find_box', None)):
                    return epub.close_find
                sidebar = getattr(epub, 'sidebar', None)
                if (contains(view, epub) and sidebar is not None
                        and not sidebar.expanded and sidebar.sidebar_open):
                    return sidebar.show_detail
            for tools in (getattr(owner, 'pdf_tools', None),
                          getattr(epub, 'tools', None) if getattr(epub, 'sidebar', None) is None else None):
                if tools is not None and contains(view, tools.panel):
                    return tools.close
        return None

    def reader_back_action(self, view):
        """Choose a system-Back tool action for the active reader."""
        from .routes import contains
        readers = getattr(self, 'readers', None)
        reader = readers.active if readers is not None else None
        if reader is not None and contains(view, getattr(reader, 'library_view', None)):
            chapters = getattr(reader, 'chapter_sidebar', None)
            if chapters is not None and not chapters.expanded and chapters.sidebar_open:
                return chapters.show_detail

        private = getattr(self, 'private_sessions', None)
        reader = private.active if private is not None else None
        if reader is not None and contains(view, getattr(reader, 'crypt_view', None)):
            epub = getattr(reader, 'provider_epub_view', None)
            if epub is not None and contains(view, getattr(epub, 'find_box', None)):
                return epub.close_find
            chapters = getattr(epub, 'sidebar', None)
            if chapters is not None and not chapters.expanded and chapters.sidebar_open:
                return chapters.show_detail
            tools = getattr(epub, 'tools', None)
            if chapters is None and tools is not None and contains(view, tools.panel):
                return tools.close
            tools = getattr(reader, 'pdf_tools', None)
            if tools is not None and contains(view, tools.panel):
                return tools.close

        return None

    def refresh_reader_exit(self, view):
        button = getattr(view, '_reader_close_button', None)
        if button is not None:
            from .control_icons import apply_icon
            tool = self.reader_tool_back(view)
            icon, label = ('back', 'Back to document') if tool else ('close', 'Close document')
            if button.control_icon != icon:
                apply_icon(button, icon, label)

    def reader_exit(self, view, key):
        tool = self.reader_tool_back(view)
        if tool is not None:
            tool()
            self.refresh_reader_exit(view)
            self.adaptive.render()
            return True
        return self.request_reader_close(key)

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
        from .session_workflows.transitions import transitions_for
        return transitions_for(self).request_reader_close(key)

    def keep_reader_editing(self, key):
        from .session_workflows.transitions import transitions_for
        return transitions_for(self).keep_reader_editing(key)

    @staticmethod
    def book_edits_dirty(owner):
        return any(field.value != owner.book_metadata_initial.get(name, '')
                   for name, field in getattr(owner, 'book_metadata_fields', {}).items())

    def request_book_close(self, owner):
        from .session_workflows.transitions import transitions_for
        return transitions_for(self).request_book_close(owner)

    def document_close_dialog(self, key, title, save, discard):
        from .session_workflows.transitions import transitions_for
        return transitions_for(self).document_close_dialog(key, title, save, discard)

    def reader_closed(self, key, *, refresh_roots=False):
        from .session_workflows.transitions import transitions_for
        return transitions_for(self).reader_closed(key, refresh_roots=refresh_roots)
