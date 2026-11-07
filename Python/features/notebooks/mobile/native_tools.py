"""Native drawing targets mirror the live canvas controls, never its model."""
import asyncio
import json
from traceback import extract_tb
import weakref
from .brush_presets import PREFERENCE, TOOLBAR_PRESET_LIMIT, read_presets

TOOLS = ('pen', 'erase', 'select', 'undo', 'redo')
PRESET_TOOLS = ('pen', 'preset-0', 'preset-1', 'add-preset', *TOOLS[1:])
STRIP_WIDTH = len(TOOLS) * 44
MINIMUM_TITLE_WIDTH = 96
LANDSCAPE_INSET = 16
LANDSCAPE_GAP = 12


def landscape_slots(width, strip_width):
    """Place the title and tools at thirds, clamping to the usable band."""
    width = max(0, width - 2 * LANDSCAPE_INSET)
    tool_start = min(width - strip_width, width * 2 / 3 - strip_width / 2)
    title_width = min(280, max(MINIMUM_TITLE_WIDTH, 2 * (tool_start - LANDSCAPE_GAP - width / 3)))
    title_start = max(0, min(width / 3 - title_width / 2, tool_start - LANDSCAPE_GAP - title_width))
    return title_start, title_width, max(LANDSCAPE_GAP, tool_start - title_start - title_width)


class NativeDrawingTools:
    def __init__(self, panel):
        self.panel = weakref.ref(panel)
        self.header = self.strip = self.task = self.web = None
        self.controller = None
        self.buttons = {}
        self.lock = asyncio.Lock()
        self.pending = {}
        self.epoch = 0
        self.observer_exit = None
        self.title_spacers = None

    def wide_landscape(self, controller):
        panel = self.panel()
        if panel is None:
            return False
        native = controller.view
        size = native.bounds.size
        width = float(native.safeAreaLayoutGuide.layoutFrame.size.width)
        style = panel.view.style
        return (size.width > size.height
                and width - style.margin_left - style.margin_right >= 640)

    def stacked_portrait(self, controller):
        """A narrow portrait allocation keeps its title above the tool strip."""
        size = controller.view.bounds.size
        return 0 < size.width < 540 and size.height > size.width

    def available_width(self, controller):
        panel = self.panel()
        native = controller.view
        width = float(native.safeAreaLayoutGuide.layoutFrame.size.width)
        container = getattr(panel.view._impl, 'container', None)
        if container is not None:
            measured = float(container.native.bounds.size.width) - container.left_inset - container.right_inset
            if measured > 0:
                width = min(width, measured)
        style = panel.view.style
        return width - style.margin_left - style.margin_right

    def fits(self, controller, *, inline_width=None):
        panel = self.panel()
        if panel is None or panel.closed or not getattr(panel, '_canvas_ready', False) or controller is None:
            return False
        landscape = self.wide_landscape(controller)
        if not landscape and not getattr(panel.app.presentation, 'native_notebook_toolbar', True):
            return False
        if inline_width is not None and not landscape:
            return False
        size = str(controller.traitCollection.preferredContentSizeCategory)
        strip_width = STRIP_WIDTH
        if hasattr(panel, '_brush_presets_sent'):
            presets = read_presets(panel.app.preferences.values.get(PREFERENCE, '[]'))
            if len(presets) > TOOLBAR_PRESET_LIMIT:
                return False  # Older lists remain reachable in the scrolling toolbar.
            strip_width += TOOLBAR_PRESET_LIMIT * 44
        width = self.available_width(controller) if inline_width is None else inline_width
        required = strip_width + LANDSCAPE_GAP
        if inline_width is None:
            required = strip_width + MINIMUM_TITLE_WIDTH + (
                2 * LANDSCAPE_INSET + LANDSCAPE_GAP if landscape else 16)
        return (width >= required
                and not self.stacked_portrait(controller)
                and 'Accessibility' not in size
                and not getattr(panel.view, '_reader_fullscreen', False)
                and panel.app.presentation.fold_division(panel.web) is None)

    def mount(self, header, controller, *, before=None):
        panel = self.panel()
        if self.header is header and self.web is panel.web and self.controller == controller:
            self.reflow_landscape()
            return
        self.close()
        import toga
        from toga.style import Pack
        from toga.style.pack import ROW
        from commonUtils.ui.native.icons import IconRenderer, IconSpec
        names = PRESET_TOOLS if hasattr(panel, '_brush_presets_sent') else TOOLS
        surface = panel.app.presentation.surface
        renderer = IconRenderer({name: IconSpec(symbol, fallback, ()) for name, symbol, fallback in (
            ('pen', 'pencil.tip', '✎'), ('erase', 'eraser', '▱'), ('select', 'lasso', '◌'),
            ('undo', 'arrow.uturn.backward', '↶'), ('redo', 'arrow.uturn.forward', '↷'),
            ('add-preset', 'plus', '+'))})
        self.header, self.web = header, panel.web
        self.controller = controller
        if before is None:
            header.style.direction = ROW
            header.style.align_items = 'center'
            header._title_content = toga.Box(style=Pack(flex=1, height=48, margin_left=8, margin_right=8))
            self.title_spacers = (toga.Box(), toga.Box())
        self.strip = toga.Box(style=Pack(direction=ROW, height=48))
        for name in names:
            async def click(widget=None, name=name, **kwargs):
                await self.activate(name)
            button = toga.Button(on_press=click, enabled=False, style=Pack(width=44, height=48))
            if name.startswith('preset-'):
                panel.app.presentation.bind_apple_hold(button, button._impl.native, lambda _, name=name:
                                panel.app.loop.create_task(self.activate(name, hold=True)))
                button.style.display = 'none'
            else:
                renderer.apply(button, name, {'pen': 'Brush, color and width', 'erase': 'Erase',
                    'select': 'Select / move', 'undo': 'Undo', 'redo': 'Redo',
                    'add-preset': 'Add current brush preset'}[name], preserve_layout=True)
            surface(button, foreground='text')
            self.buttons[name] = button
            if button.style.display != 'none':
                self.strip.add(button)
        # Keep the flattened iOS controls hidden until the canvas yields its toolbar.
        self.strip.style.visibility = 'hidden'
        self.strip.style.width = 44 * len(self.strip.children)
        if before is None:
            leading, gap = self.title_spacers
            header.add(leading, header._title_content, gap, self.strip)
            self.reflow_landscape()
        else:
            header.insert(list(header.children).index(before), self.strip)
        self.observer_exit = None
        self.task = panel.app.loop.create_task(self.observe())

    def reflow_landscape(self):
        if self.title_spacers is None:
            return
        from toga.style.pack import NONE
        leading, gap = self.title_spacers
        title = self.header._title_content
        if self.wide_landscape(self.controller):
            inset = LANDSCAPE_INSET
            start, width, spacing = landscape_slots(self.available_width(self.controller), self.strip.style.width)
            values = (start, width, spacing, 0, 0)
        else:
            inset = 0
            values = (0, NONE, 0, 1, 8)
        start, width, spacing, flex, title_margin = values
        for style, properties in (
            (leading.style, dict(width=start)),
            (gap.style, dict(width=spacing)),
            (title.style, dict(width=width, flex=flex, margin_left=title_margin, margin_right=title_margin)),
            (self.header.style, dict(margin_left=inset, margin_right=inset)),
        ):
            for key, value in properties.items():
                if getattr(style, key) != value:
                    setattr(style, key, value)

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

    def owns_controller(self, panel):
        if not panel.app.active_host:
            return False
        adapter = panel.app.native_host.adapter
        controller = adapter.content_controller(panel.app.native_host.state.destination)
        return (self.controller is not None and controller is not None
                and controller.ptr.value == self.controller.ptr.value)

    def visible(self, panel):
        from commonUtils.ui.native.keyboard import native_value
        if not self.owns_controller(panel):
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

    def owns_strip(self, panel):
        return (panel is not None and not panel.closed and panel.web is self.web
                and self.header is not None and self.header.parent is not None
                and self.strip is not None and self.strip.parent is self.header)

    def current(self):
        panel = self.panel()
        return self.owns_strip(panel) and self.visible(panel)

    async def refresh(self, action=None):
        panel = self.panel()
        if not self.current():
            for button in self.buttons.values():
                button.enabled = False
            return
        web, header, epoch = self.web, self.header, self.epoch
        script = 'window.notebookNativeTools?.(' + json.dumps(action) + ')'
        raw = await self.query(script)
        if self.epoch != epoch or self.web is not web or self.header is not header or not self.current():
            return
        # WK can return None before the canvas installs its JavaScript hook.
        # Keep observing, with native buttons hidden until a lease is available.
        value = json.loads(raw) if raw is not None else None
        if value is None:
            self.strip.style.visibility = 'hidden'
            for button in self.buttons.values():
                button.enabled = False
            return
        if set(value) != set(self.buttons) or any(type(row.get(key)) is not bool
                for row in value.values() for key in ('disabled', 'active')):
            raise ValueError('The notebook drawing controls are not ready.')
        surface = panel.app.presentation.surface
        visible_index = 0
        for name, row in value.items():
            button = self.buttons[name]
            visible = row.get('visible', True)
            if 'visible' in row:
                # The iOS backend flattens buttons into the parent view.
                # Unmount empty slots so they relinquish their native space.
                button.style.display = 'pack' if visible else 'none'
                if visible and button.parent is not self.strip:
                    self.strip.insert(visible_index, button)
                elif not visible and button.parent is self.strip:
                    self.strip.remove(button)
            button.enabled = visible and not (row['disabled'] or panel.busy or panel.native_input_pending)
            if visible and name.startswith('preset-'):
                self.paint_preset(button, row, panel.app.presentation.accessible_name)
            surface(button, background='hover' if row['active'] else 'surface', foreground='text')
            visible_index += visible
        width = 44 * visible_index
        if 'add-preset' in value and self.strip.style.width != width:
            self.strip.style.width = width
            self.reflow_landscape()
        self.strip.style.visibility = 'visible'

    @staticmethod
    def paint_preset(button, row, accessible_name):
        from rubicon.objc import ObjCClass
        button._preset_id = row['preset_id']
        visual = (row['label'], tuple(row['preset']), tuple(row['rgb']))
        if getattr(button, '_preset_visual', None) == visual:
            return
        label, (tool, _, width), rgb = visual
        symbols = {12: 'paintbrush.pointed', 13: 'pencil', 14: 'pencil', 15: 'pencil.tip',
                   16: 'pencil.tip.crop.circle', 17: 'pencil.tip', 18: 'highlighter',
                   21: 'signature', 23: 'paintbrush'}
        images = ObjCClass('UIImage')
        image = images.systemImageNamed(symbols[tool]) or images.systemImageNamed('pencil.tip')
        config = ObjCClass('UIImageSymbolConfiguration').configurationWithPointSize(15 + 2 * width)
        if image is not None and max(rgb) != min(rgb):
            red, green, blue = (channel / 255 for channel in rgb)
            tint = ObjCClass('UIColor').colorWithRed(red, green=green, blue=blue, alpha=1)
            image = image.imageWithTintColor(tint, renderingMode=1)
        button._impl.native.setImage(image, forState=0)
        button._impl.native.setPreferredSymbolConfiguration(config, forImageInState=0)
        accessible_name(button, 'Use preset ' + label + '. Touch and hold for actions.')
        button._preset_visual = visual

    def anchor(self, name):
        native = self.buttons[name]._impl.native
        rect = native.convertRect(native.bounds, toView=self.web._impl.native)
        return [float(rect.origin.x), float(rect.origin.y),
                float(rect.size.width), float(rect.size.height)]

    async def activate(self, name, *, hold=False):
        if name not in PRESET_TOOLS:
            raise ValueError('Unknown notebook drawing control.')
        epoch = self.epoch
        async with self.lock:
            try:
                panel = self.panel()
                if (panel is not None and self.epoch == epoch and self.current()
                        and not panel.busy and not panel.native_input_pending):
                    action = dict(name=name, anchor=self.anchor(name))
                    preset_id = getattr(self.buttons[name], '_preset_id', None)
                    if preset_id is not None:
                        action['preset'] = preset_id
                    if hold:
                        action['hold'] = True
                    await self.refresh(action)
            except Exception:
                if self.epoch == epoch:
                    self.close()

    async def observe(self):
        epoch = self.epoch
        try:
            # Native attachment can trail logical mounting on the first layout
            # turn. Keep the untouched buttons disabled until visibility agrees.
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 1
            while (self.epoch == epoch and self.owns_strip(panel := self.panel())
                   and self.owns_controller(panel) and not self.visible(panel)
                   and loop.time() < deadline):
                await asyncio.sleep(.05)
            while self.epoch == epoch and self.current():
                if not self.lock.locked():
                    async with self.lock:
                        await self.refresh()
                await asyncio.sleep(.5)
            if self.epoch == epoch:
                self.observer_exit = (
                    'strip retired' if not self.owns_strip(panel := self.panel())
                    else 'controller replaced' if not self.owns_controller(panel)
                    else 'header outside visible window'
                )
                self.close()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if self.epoch == epoch:
                site = extract_tb(error.__traceback__)[-1]
                self.observer_exit = f'{type(error).__name__} at {site.name}:{site.lineno}'
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
        if header is not None and self.title_spacers is not None:
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
            header.style.margin_left = header.style.margin_right = 0
        elif header is not None and self.strip is not None and self.strip.parent is header:
            header.remove(self.strip)
        self.title_spacers = None
        self.strip = self.web = self.controller = None
        self.buttons = {}
