"""One creation route that adapts its two retained steps to the available pane."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, NONE

from .fold_layout import division
from .layout_participants import participants


def pane_sizes(width, height, fold):
    if fold is not None:
        if fold.vertical and min(fold.x, width - fold.x - fold.width) >= 265:
            return round(fold.x), round(fold.width)
        return None
    if width >= 640 and height >= 440:
        return round(width * .44), 12
    return None


def mount(parent, widget, index):
    if index is None:
        if widget.parent is parent:
            parent.remove(widget)
    elif widget.parent is not parent:
        parent.insert(min(index, len(parent.children)), widget)


class CreationNameForm(toga.ScrollContainer):
    """Allow a single full-size input above a short landscape keyboard.

    Toga's inherited 100-point minimum would overflow beneath the keyboard
    once the pinned format tabs occupy the top of the naming pane.
    """
    _MIN_HEIGHT = 44


class CreationLocation:
    """Creation guidance around the existing browser and its navigation callbacks."""
    def __init__(self, picker):
        self.picker = picker
        self.title = toga.Label('Choose a folder', style=Pack(flex=1, font_size=18))
        self.heading = toga.Box(children=[self.title], style=Pack(direction=ROW,
            align_items='center', height=48, margin_left=12, margin_right=12))
        picker.edit_name = toga.Button('Back', on_press=picker.show_creation_name, style=Pack(height=44))
        picker.picker_new_folder.text = '+ New folder'
        picker.save_as_storage.style.flex = 1
        self.storage = toga.Box(children=[picker.save_as_storage, picker.picker_new_folder],
            style=Pack(direction=ROW, margin_left=12, margin_right=12))
        self.crumbs = toga.Box(style=Pack(direction=ROW))
        self.path = CreationNameForm(content=self.crumbs, horizontal=True, vertical=False,
            style=Pack(height=44, flex=1))
        self.header = toga.Box(children=[picker.picker_header], style=Pack(direction=COLUMN))
        self.caption_index = list(picker.picker_header.children).index(picker.picker_header.caption)

    def reflow(self, paired, short, apple):
        p = self.picker
        self.heading.style.height = 0 if short else 48
        mount(self.heading, self.title, None if short else len(self.heading.children))
        target = self.storage if short else self.heading
        if p.edit_name.parent is not target and p.edit_name.parent is not None:
            p.edit_name.parent.remove(p.edit_name)
        mount(target, p.edit_name, 0 if not paired and not apple else None)

    def update(self, label, folder):
        p = self.picker
        self.crumbs.clear()
        # Keep the browser's Up/search controls and row behavior intact. These
        # links call the same guarded navigation used by its folder rows.
        targets = [(label, '')]
        parts = folder.split('/') if folder else []
        targets.extend((part, '/'.join(parts[:i + 1])) for i, part in enumerate(parts))
        for i, (caption, path) in enumerate(targets):
            if i:
                self.crumbs.add(toga.Label('›', style=Pack(margin_left=2, margin_right=2, margin_top=12)))
            async def navigate(widget, target=(label, path), **kwargs):
                await p.browser_editor_location(target)
            button = toga.Button(caption, on_press=navigate, style=Pack(height=44))
            button.enabled = i < len(targets) - 1
            button._creation_parent_link = i < len(targets) - 1
            self.crumbs.add(button)
        bar = p.picker_header
        mount(bar, self.path, self.caption_index if folder else None)
        mount(bar, bar.caption, None if folder else self.caption_index)
        if not folder:
            p.picker_header.folder_name.text = 'Locations' if label == 'All files' else label

    def set_enabled(self, enabled):
        for child in self.crumbs.children:
            if isinstance(child, toga.Button):
                child.enabled = enabled and child._creation_parent_link


class CreationFormats:
    """Compact format tabs and keyboard-adaptive cards for wide panes."""
    descriptions = {'txt': 'Simple writing, no formatting',
                    'md': 'Notes with links and formatting',
                    'rmdoc': 'Handwriting and sketches'}
    tab_titles = {'txt': 'Text', 'md': 'Markdown', 'rmdoc': 'reMarkable Notebook'}
    tab_weights = {'txt': 1, 'md': 1.65, 'rmdoc': 2.6}

    def __init__(self, picker):
        self.picker = picker
        self.name_label = picker.name_view.children[0]
        self.compact = False
        self.tabbed = False
        from commonUtils.ui.native.forms import FittedLabel
        self.summary = FittedLabel('', style=Pack(flex=1, font_size=13))
        self.change = toga.Button('Change', on_press=self.expand, style=Pack(height=44))
        self.row = toga.Box(children=[self.summary], style=Pack(direction=ROW, align_items='center',
            margin_left=20, margin_right=20, height=44))
        if len(picker.creation_choices) > 1:
            self.row.add(self.change)
        self.cards = toga.Box(style=Pack(direction=COLUMN, margin_top=8))
        self.buttons = {}
        self.tab_buttons = {}
        self.tabs = toga.Box(style=Pack(direction=ROW, align_items='center', height=52,
            margin_left=12, margin_right=12))
        self.label = toga.Label('Format', style=Pack(font_size=13, margin_top=16, margin_bottom=8))
        from .appearance import described_button
        for title, extension in picker.creation_choices:
            def select(widget, label=title, **kwargs):
                if not picker.cloud_busy:
                    picker.creation_type.value = label
            button = toga.Button(title, on_press=select, style=Pack(height=64, margin_bottom=8))
            described_button(button, self.descriptions[extension])
            self.cards.add(button)
            self.buttons[title] = button
            tab = toga.Button(self.tab_titles[extension], on_press=select,
                style=Pack(flex=self.tab_weights[extension], height=48, font_size=13, margin=2))
            self.tabs.add(tab)
            self.tab_buttons[title] = tab
        self.update()

    def update(self):
        from .appearance import surface, accessible_name
        title = self.picker.creation_type.value
        extension = dict(self.picker.creation_choices)[title]
        self.summary.text = {'txt': 'Plain text', 'md': 'Markdown', 'rmdoc': 'Remarkable'}[extension] + ' · .' + extension
        accessible_name(self.change, 'Change document format')
        for label, button in self.buttons.items():
            selected = label == title
            surface(button, background='hover' if selected else 'surface', foreground='text',
                    outlined=selected, eink_selected=selected)
            accessible_name(button, label + (', selected' if selected else ''))
        for label, button in self.tab_buttons.items():
            selected = label == title
            surface(button, radius=8, background='hover' if selected else 'surface',
                    foreground='text', outlined=selected, eink_selected=selected)
            button.style.font_weight = 'bold' if selected else 'normal'
            accessible_name(button, button.text + (', selected' if selected else ''))
            backend = type(button._impl).__module__
            if backend.startswith('toga_iOS.'):
                button._impl.native.accessibilityTraits = 1 | (4 if selected else 0)
            elif backend.startswith('toga_android.'):
                button._impl.native.setSelected(selected)
        self.set_enabled(not self.picker.cloud_busy)

    def set_enabled(self, enabled):
        self.change.enabled = enabled
        if self.picker.notebook_templates is not None:
            self.picker.notebook_templates.set_enabled(enabled)
        for button in (*self.buttons.values(), *self.tab_buttons.values()):
            button.enabled = enabled

    def fit_tab(self, button, extension, width):
        from commonUtils.ui.native.forms import fit_text, wrap_text
        if not type(button._impl).__module__.startswith('toga_android.'):
            fit_text(button, width)
            return
        # Android's themed button font and content padding can differ from
        # Pack's requested font size. Measure the live control, not an estimate.
        import math
        native = button._impl.native
        density = native.getResources().getDisplayMetrics().density
        text_width = max(24, width * density - native.getCompoundPaddingLeft() - native.getCompoundPaddingRight())
        rendered = wrap_text(self.tab_titles[extension], text_width, native.getPaint().measureText)
        lines = len(rendered.split('\n'))
        native.setSingleLine(False)
        native.setMaxLines(lines)
        native.setEllipsize(None)
        button._impl.set_text(rendered)
        metrics = native.getPaint().getFontMetricsInt()
        font_padding = max(0, metrics.bottom - metrics.top - native.getLineHeight())
        button._creation_tab_height = max(44, math.ceil((native.getLineHeight() * lines
            + font_padding + native.getCompoundPaddingTop() + native.getCompoundPaddingBottom()) / density))

    def fit(self, keyboard, height, width):
        # Use remaining viewport space, including keyboard and navigation
        # reservations, rather than a device name or orientation.
        layout = self.picker.creation_layout
        paired = layout is not None and layout.paired
        self.tabbed = not paired and (width < 640 or self.picker.app.main_window.size.height < 440)
        compact = not self.tabbed and keyboard and (height < 560 or width < 320)
        from commonUtils.ui.native.forms import fit_text
        fit_text(self.summary, max(120, width - 130))
        self.compact = compact
        view = self.picker.name_view
        if self.picker.notebook_templates is not None:
            self.picker.notebook_templates.fit(width)
        short = self.tabbed and keyboard and height < 140
        self.picker.save_as_name.style.height = 44 if short else 48
        # Reserve the short viewport for the field itself. Avoid partially
        # visible labels behind the pinned tabs; keep validation errors retained.
        mount(view, self.name_label, None if short else 0)
        mount(view, self.picker.effective_name,
              None if short and self.picker._creation_name_valid else len(view.children))
        if hasattr(self.picker, 'name_content'):
            mount(self.picker.name_content, self.row, 0 if compact else None)
            mount(self.picker.name_content, self.tabs, 0 if self.tabbed else None)
        view.style.margin_top = view.style.margin_bottom = (
            0 if short else 8 if compact or self.tabbed else 20)
        mount(view, self.label, None if compact or self.tabbed else 2)
        mount(view, self.cards, None if compact or self.tabbed else 3)
        if self.tabbed:
            total = sum(self.tab_weights[ext] for _, ext in self.picker.creation_choices)
            for label, extension in self.picker.creation_choices:
                self.fit_tab(self.tab_buttons[label], extension,
                             max(44, (width - 24) * self.tab_weights[extension] / total - 4))
            height = max(getattr(button, '_creation_tab_height', button.style.height if '\n' in button.text else 44)
                         for button in self.tab_buttons.values())
            for button in self.tab_buttons.values():
                button.style.height = height
                button.style.margin_top = button.style.margin_bottom = 0 if short else 2
            self.tabs.style.height = height + (0 if short else 4)

    def expand(self, widget=None, **kwargs):
        if self.picker.cloud_busy:
            return
        from .keyboard import dismiss_picker_keyboard
        dismiss_picker_keyboard(self.picker)
        self.picker.fit_keyboard(False)


class CreationLayout(toga.Box):
    def __init__(self, picker):
        super().__init__(style=Pack(direction=COLUMN, flex=1))
        self.picker = picker
        self.paired = False
        self.signature = None
        self.gutter = toga.Box()
        self.name_cancel = picker.name_actions.children[0]
        self.location_cancel = picker.picker_actions.children[0]
        self.apple = type(self._impl).__module__.startswith('toga_iOS.')
        if self.apple:
            picker.next_button._toolbar_prominent = picker.picker_primary._toolbar_prominent = True
        participants(picker.app).register('document-creation', self, CreationLayout.on_resize)

    def on_resize(self, frame):
        if self.picker.creation_layout is self and self.picker.visible():
            self.reflow()
            p = self.picker
            pending = getattr(self, '_location_load', None)
            if (self.paired and p.editor_picker_location is None and not p.cloud_busy
                    and (pending is None or pending.done())):
                async def load():
                    if p.creation_layout is self and self.paired and p.visible():
                        await p.load_picker_location()
                self._location_load = p.app.loop.create_task(load())

    def reflow(self):
        p = self.picker
        native = getattr(self._impl, 'native', None)
        width = p.app.adaptive.content_width(p.app.native_host.state.destination, margin=0)
        height = p.app.main_window.size.height
        if self.apple:
            width = float(native.bounds.size.width) or width
        elif native is not None and hasattr(native, 'getResources'):
            # The host allocates the new pane before Android lays out its children.
            # Reading this child's old width here would keep the previous split.
            # Android resizes the activity for the IME. Use the window allocation
            # to keep both panes mounted while the user edits the name.
            height = native.getResources().getConfiguration().screenHeightDp
        sizes = pane_sizes(width, height, division(p, self))
        if self.paired and sizes is None and p._compact_keyboard:
            field = getattr(p.save_as_name._impl, 'native', None)
            focused = bool(field.isFirstResponder) if self.apple else bool(field and field.hasFocus())
            if focused:
                p.panel = p.name_panel
        naming = p.panel is p.name_panel
        signature = (sizes, naming, round(width))
        if self.signature == signature:
            return
        self.signature = signature
        self.paired = sizes is not None
        from commonUtils.ui.native.forms import fit_text
        right_width = width - sum(sizes) if sizes else width
        fit_text(p.picker_destination, max(120, right_width - 32))
        fit_text(p.save_as_status.label, max(120, right_width - 32))
        self.style.direction = ROW if sizes else COLUMN
        if sizes:
            p.name_panel.style.flex = 0
            p.name_panel.style.width, self.gutter.style.width = sizes
        else:
            p.name_panel.style.width = NONE
            p.name_panel.style.flex = 1
        mount(self, p.name_panel, 0 if naming or sizes else None)
        mount(self, self.gutter, 1 if sizes else None)
        mount(self, p.location_panel, (2 if sizes else 0) if sizes or not naming else None)

        # The folder header's arrow stays local to the browser. The separate
        # Back to name action exists only when the name is on a different page.
        p.creation_location.reflow(bool(sizes), height < 440, self.apple)
        mount(p.name_actions, self.name_cancel, 0 if not self.apple else None)
        mount(p.picker_actions, self.location_cancel, 0 if not sizes and not self.apple else None)
        mount(p.name_actions, p.next_button, 1 if naming and not sizes and not self.apple else None)
        # UIKit projects both naming actions into its navigation bar. An empty
        # in-body action box must not reserve footer space above the keyboard.
        mount(p.name_panel, p.name_actions, None if self.apple else 1)
        mount(p.picker_actions, p.picker_primary, 1 if sizes or not self.apple else None)
        mount(p.location_panel, p.picker_actions,
              None if self.apple and not sizes else len(p.location_panel.children))
        p.fit_keyboard(p._compact_keyboard)
        if self.apple:
            self._ios_toolbar_buttons = [] if sizes else [p.next_button if naming else p.picker_primary]
            self._ios_toolbar_leading = [self.name_cancel if sizes or naming else p.edit_name]
            self._ios_toolbar_replaces_back = True
            self.name_cancel._toolbar_symbol = 'xmark'
            p.edit_name._toolbar_symbol = 'chevron.left'
            self._ios_toolbar_title = lambda: 'New document' if self.paired else (
                'Name your file' if p.panel is p.name_panel else 'Choose a folder')
            if p.visible():
                from .ios_toolbar import sync_screen
                sync_screen(p.app, self, p.app.native_host.state.destination)
