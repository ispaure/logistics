"""Native drawing targets mirror the live canvas controls, never its model."""
import asyncio
import json
import weakref

TOOLS = ('pen', 'erase', 'select', 'undo', 'redo')
STRIP_WIDTH = len(TOOLS) * 44
MINIMUM_TITLE_WIDTH = 96


class NativeDrawingTools:
    def __init__(self, panel):
        self.panel = weakref.ref(panel)
        self.header = self.strip = self.task = self.web = None
        self.controller = None
        self.buttons = {}
        self.lock = asyncio.Lock()
        self.pending = {}
        self.epoch = 0

    def fits(self, controller):
        panel = self.panel()
        if panel is None or panel.closed or not getattr(panel, '_canvas_ready', False):
            return False
        native = controller.view
        size = str(controller.traitCollection.preferredContentSizeCategory)
        width = float(native.safeAreaLayoutGuide.layoutFrame.size.width)
        style = panel.view.style
        return (width - style.margin_left - style.margin_right >= MINIMUM_TITLE_WIDTH + STRIP_WIDTH + 16
                and 'Accessibility' not in size
                and not getattr(panel.view, '_reader_fullscreen', False)
                and panel.app.presentation.fold_division(panel.web) is None)

    def mount(self, header, controller):
        panel = self.panel()
        if self.header is header and self.web is panel.web and self.controller == controller:
            return
        self.close()
        import toga
        from toga.style import Pack
        from toga.style.pack import ROW
        from commonUtils.ui.native.icons import IconRenderer, IconSpec
        surface = panel.app.presentation.surface
        renderer = IconRenderer({name: IconSpec(symbol, fallback, ()) for name, symbol, fallback in (
            ('pen', 'pencil.tip', '✎'), ('erase', 'eraser', '▱'), ('select', 'lasso', '◌'),
            ('undo', 'arrow.uturn.backward', '↶'), ('redo', 'arrow.uturn.forward', '↷'))})
        self.header, self.web = header, panel.web
        self.controller = controller
        header.style.direction = ROW
        header.style.align_items = 'center'
        header._title_content = toga.Box(style=Pack(flex=1, height=48, margin_left=8, margin_right=8))
        self.strip = toga.Box(style=Pack(direction=ROW, width=STRIP_WIDTH, height=48))
        for name in TOOLS:
            async def click(widget=None, name=name, **kwargs):
                await self.activate(name)
            button = toga.Button(on_press=click, enabled=False, style=Pack(width=44, height=48))
            renderer.apply(button, name, {'pen': 'Brush, color and width', 'erase': 'Erase',
                'select': 'Select / move', 'undo': 'Undo', 'redo': 'Redo'}[name], preserve_layout=True)
            surface(button, foreground='text')
            self.buttons[name] = button
            self.strip.add(button)
        header.add(header._title_content, self.strip)
        self.task = panel.app.loop.create_task(self.observe())

    async def query(self, script, *, web=None):
        web = web or self.web
        key = id(web)
        previous = self.pending.get(key)
        if previous is not None and not previous.done():
            raise TimeoutError('The notebook controls are still responding.')
        future = asyncio.ensure_future(web.evaluate_javascript(script))
        self.pending[key] = future
        reference = weakref.ref(self)
        def completed(done):
            try:
                done.result()
            except BaseException:
                pass
            owner = reference()
            if owner is not None and owner.pending.get(key) is done:
                owner.pending.pop(key, None)
        future.add_done_callback(completed)
        # Cancellation retires only this waiter, never the native WK completion.
        done, _ = await asyncio.wait((future,), timeout=1)
        if not done:
            raise TimeoutError('The notebook controls are still responding.')
        return future.result()

    def visible(self, panel):
        from commonUtils.ui.native.keyboard import native_value
        if not panel.app.active_host:
            return False
        adapter = panel.app.native_host.adapter
        controller = adapter.content_controller(panel.app.native_host.state.destination)
        if self.controller is None or controller.ptr.value != self.controller.ptr.value:
            return False
        native = self.header._impl.native
        window = native_value(native.window)
        expected = panel.app.main_window._impl.native
        if window is None or window.ptr.value != expected.ptr.value:
            return False
        # Retained navigation containers can remain attached while hidden.
        for _ in range(24):
            if bool(native_value(native.isHidden)):
                return False
            parent = native_value(native.superview)
            if parent is None:
                return True
            native = parent
        return False

    def current(self):
        panel = self.panel()
        return (panel is not None and not panel.closed and panel.web is self.web
                and self.header is not None and self.header.parent is not None
                and self.strip is not None and self.strip.parent is self.header
                and self.visible(panel))

    async def refresh(self, action=None):
        panel = self.panel()
        if not self.current() or panel.busy or panel.native_input_pending:
            for button in self.buttons.values():
                button.enabled = False
            return
        web, header, epoch = self.web, self.header, self.epoch
        script = 'window.notebookNativeTools?.(' + json.dumps(action) + ')'
        raw = await self.query(script)
        if self.epoch != epoch or self.web is not web or self.header is not header or not self.current():
            return
        value = json.loads(raw)
        if set(value) != set(TOOLS) or any(set(row) != {'disabled', 'active'}
                or any(type(item) is not bool for item in row.values()) for row in value.values()):
            raise ValueError('The notebook drawing controls are not ready.')
        surface = panel.app.presentation.surface
        for name, row in value.items():
            button = self.buttons[name]
            button.enabled = not row['disabled']
            surface(button, background='hover' if row['active'] else 'surface', foreground='text')

    def anchor(self, name):
        native = self.buttons[name]._impl.native
        rect = native.convertRect(native.bounds, toView=self.web._impl.native)
        return [float(rect.origin.x), float(rect.origin.y),
                float(rect.size.width), float(rect.size.height)]

    async def activate(self, name):
        if name not in TOOLS:
            raise ValueError('Unknown notebook drawing control.')
        epoch = self.epoch
        async with self.lock:
            try:
                if self.epoch == epoch and self.current():
                    await self.refresh(dict(name=name, anchor=self.anchor(name)))
            except Exception:
                if self.epoch == epoch:
                    self.close()

    async def observe(self):
        epoch = self.epoch
        try:
            while self.epoch == epoch and self.current():
                if not self.lock.locked():
                    async with self.lock:
                        await self.refresh()
                await asyncio.sleep(.5)
            if self.epoch == epoch:
                self.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            if self.epoch == epoch:
                self.close()

    def close(self):
        self.epoch += 1
        task, self.task = self.task, None
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        if task is not None and task is not current:
            task.cancel()  # query() does not cancel its native JS future.
        old_web = self.web
        panel = self.panel()
        if old_web is not None and panel is not None:
            async def restore():
                async with self.lock:
                    if self.web is old_web and self.current():
                        return  # A new mounted strip owns this same canvas lease.
                    try:
                        await self.query('window.notebookNativeTools?.(false)', web=old_web)
                        current_panel = self.panel()
                        if current_panel is not None and current_panel.web is old_web:
                            current_panel.refresh_fold()
                    except Exception:
                        pass
            # Own only this bounded response task; no notebook/model mutation.
            panel.app.loop.create_task(restore())
        header, self.header = self.header, None
        if header is not None and hasattr(header, '_title_content'):
            title = getattr(header, '_mounted_title', None)
            if title is not None and title.superview == header._title_content._impl.native:
                header._impl.native.addSubview(title)
                title.frame = header._impl.native.bounds
            for child in list(header.children):
                header.remove(child)
            del header._title_content
            from toga.style.pack import COLUMN
            header.style.direction = COLUMN
            header.style.height = 37
        self.strip = self.web = self.controller = None
        self.buttons = {}
