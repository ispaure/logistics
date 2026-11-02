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


class CreationLayout(toga.Box):
    def __init__(self, picker):
        super().__init__(style=Pack(direction=COLUMN, flex=1))
        self.picker = picker
        self.paired = False
        self.signature = None
        self.gutter = toga.Box()
        self.prompt = toga.Box(children=[
            toga.Label('Save location', style=Pack(font_weight='bold', margin_bottom=8)),
            toga.Label('Choose a name and file type first.')],
            style=Pack(direction=COLUMN, flex=1, margin=12))
        self.name_cancel = picker.name_actions.children[0]
        self.location_cancel = picker.picker_actions.children[0]
        self.apple = type(self._impl).__module__.startswith('toga_iOS.')
        if self.apple:
            picker.next_button._toolbar_prominent = picker.picker_primary._toolbar_prominent = True
        participants(picker.app).register('document-creation', self, CreationLayout.on_resize)

    def on_resize(self, frame):
        if self.picker.creation_layout is self and self.picker.visible():
            self.reflow()

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
        was_paired = self.paired
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
        mount(self, self.prompt, 2 if sizes and naming else None)
        mount(self, p.location_panel, (2 if sizes else 0) if not naming else None)

        # The folder header's arrow stays local to the browser. The separate
        # Back to name action exists only when the name is on a different page.
        if not self.apple:
            mount(p.save_as_storage.parent, p.edit_name, 0 if not sizes else None)
        mount(p.name_actions, self.name_cancel, 0 if not self.apple else None)
        mount(p.picker_actions, self.location_cancel, 0 if not sizes else None)
        mount(p.name_actions, p.next_button, 1 if naming and (sizes or not self.apple) else None)
        mount(p.picker_actions, p.picker_primary, 1 if sizes or not self.apple else None)
        if was_paired != self.paired and p._compact_keyboard:
            p.fit_keyboard(True)
        if self.apple:
            self._ios_toolbar_buttons = [] if sizes else [p.next_button if naming else p.picker_primary]
            self._ios_toolbar_leading = [self.name_cancel if sizes or naming else p.edit_name]
            self._ios_toolbar_replaces_back = True
            self.name_cancel._toolbar_symbol = 'xmark'
            p.edit_name._toolbar_symbol = 'chevron.left'
            self._ios_toolbar_title = lambda: 'New document' if self.paired else (
                'Name your file' if p.panel is p.name_panel else 'Choose location')
            if p.visible():
                from .ios_toolbar import sync_screen
                sync_screen(p.app, self, p.app.native_host.state.destination)
