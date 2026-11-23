"""Local File Browser controls and viewport-owned thumbnails."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from functools import partial
from pathlib import PurePosixPath
from threading import Event
from weakref import ref

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW

from commonUtils.ui.native.presentation import allow_label_to_shrink

from .appearance import accessible_name, batch_surfaces, surface
from .browser_ui import FileBrowser, browser_command
from .control_icons import apply_icon, icon_button
from .ui_metrics import CONTROL_TEXT, TOUCH_TARGET


_TILE_TITLE_INSET = 8


def _style_tile_title(button):
    button.style.update(height=72, font_size=CONTROL_TEXT)
    allow_label_to_shrink(button)
    impl = button._impl
    backend = type(impl).__module__
    if backend.startswith('toga_iOS.'):
        impl.native.contentHorizontalAlignment = 0
    elif backend.startswith('toga_android.'):
        native = impl.native
        padding = impl.scale_in(_TILE_TITLE_INSET)
        native.setPaddingRelative(padding, 0, padding, 0)
        native.setGravity(17)


def _android_tile_title(title, paint, width, lines):
    from android.text import StaticLayout, TextUtils

    if lines == 1:
        return str(TextUtils.ellipsize(title, paint, float(width), TextUtils.TruncateAt.MIDDLE))

    # Android only supports end ellipsis on a multiline TextView. Let its
    # layout choose the first break. Keep the longest suffix on the next line.
    length = len(title.encode('utf-16-le')) // 2
    layout = StaticLayout.Builder.obtain(title, 0, length, paint, width).build()
    if layout.getLineCount() <= lines:
        return title
    split = layout.getLineEnd(0)
    first = str(TextUtils.substring(title, 0, split)).rstrip()
    if paint.measureText(first) < width / 2:
        # A short word followed by a long unbroken token can leave the
        # first line nearly empty. Fill it at a grapheme boundary instead.
        from android.icu.text import BreakIterator
        boundaries = BreakIterator.getCharacterInstance()
        boundaries.setText(title)
        limit = paint.breakText(title, True, float(width), None)
        split = max(split, boundaries.preceding(min(limit + 1, length)))
        first = str(TextUtils.substring(title, 0, split)).rstrip()
    rest = TextUtils.substring(title, split, length)
    last = TextUtils.ellipsize(rest, paint, float(width), TextUtils.TruncateAt.START)
    return first + '\n' + str(last)


def _install_android_tile_title(button):
    impl = button._impl

    # Keep Toga's logical text intact for checkmarks, actions and recycling.
    # Set only the visible native caption, after Pack allocates its actual width.
    implementation = type(impl)
    target = ref(impl)
    title = displayed = button.text
    fitted_size = None
    multiline = False

    def set_text(text):
        nonlocal title, displayed, fitted_size
        title = displayed = text
        fitted_size = None
        implementation.set_text(target(), text)

    def set_bounds(x, y, width, height):
        nonlocal displayed, fitted_size, multiline
        current = target()
        implementation.set_bounds(current, x, y, width, height)
        size = width, height
        if fitted_size == size or not title or width <= 0 or height <= 0:
            return
        fitted_size = size
        view = current.native
        available = current.scale_in(width) - 2 * current.scale_in(_TILE_TITLE_INSET)
        if available <= 0:
            return
        display = ' '.join(title.splitlines())
        paint = view.getPaint()
        if paint.measureText(display) > available:
            if not multiline:
                # Short captions use the default button layout. Configure
                # wrapping only when the available width actually needs it.
                view.setSingleLine(False)
                view.setMaxLines(2)
                view.setBreakStrategy(0)  # Match StaticLayout's simple line breaking.
                view.setHyphenationFrequency(0)
                multiline = True
            lines = 2 if current.scale_in(height) >= 2 * view.getLineHeight() else 1
            display = _android_tile_title(display, paint, available, lines)
        if display != displayed:
            implementation.set_text(current, display)
            displayed = display

    impl.get_text = lambda: title
    impl.set_text = set_text
    impl.set_bounds = set_bounds
    impl._tile_title_layout = True


def _tile_filename(button):
    backend = type(button._impl).__module__
    if backend.startswith('toga_iOS.'):
        title = button._impl.native.titleLabel
        title.numberOfLines = 2
        title.textAlignment = 1
        title.lineBreakMode = 5  # NSLineBreakByTruncatingMiddle
    elif backend.startswith('toga_android.') and not getattr(button._impl, '_tile_title_layout', False):
        _install_android_tile_title(button)
    accessible_name(button, button.text)


class FileDetailsPanel(toga.Box):
    """Keep file information detached from browser navigation."""

    def __init__(self, browser, owner):
        from commonUtils.ui.native.forms import FittedLabel, fit_section
        from .speech_overlay import SpeechOverlay

        super().__init__(style=Pack(direction=COLUMN, margin=16, flex=1, gap=8))
        self.browser = ref(browser)
        app = browser._app
        self.overlay = None
        entry = browser.tree.entries.get(browser.selected) if browser.tree is not None else None
        title = toga.Label('Folder details' if entry and entry.container else 'File details',
                           style=Pack(flex=1, font_size=17, font_weight='bold'))
        close = icon_button('close', 'Close details', on_press=self.hide)
        fields = toga.Box(style=Pack(direction=COLUMN, gap=12))
        name = entry.label if entry is not None else ''
        fields.add(FittedLabel(name, style=Pack(font_size=21, font_weight='bold')))
        for child in browser.info.children:
            if isinstance(child, toga.Label):
                text = child.text
            elif isinstance(child, toga.MultilineTextInput):
                text = child.value
            else:
                continue
            label, _, value = text.partition(': ')
            if label == 'Name':
                continue
            caption = surface(FittedLabel(label, style=Pack(font_size=12)),
                              background='transparent', foreground='muted', outlined=False)
            fields.add(toga.Box(children=[caption, FittedLabel(value, style=Pack(font_size=15))],
                                style=Pack(direction=COLUMN, gap=3)))
        self.preview = toga.Box(style=Pack(direction=COLUMN, align_items=CENTER))
        fields.add(self.preview)
        width = min(440, max(100, app.main_window.size.width - 64))
        fit_section(fields, width - 32)
        self.overlay_height = min(480, 124 + 56 * (len(fields.children) - 1))
        self.add(toga.Box(children=[title, close], style=Pack(direction=ROW, align_items=CENTER)),
                 toga.ScrollContainer(content=fields, horizontal=False, style=Pack(flex=1)))
        self.overlay = SpeechOverlay(self, owner, app, label=title.text, centered=True,
                                     dim=True, width_limit=440, android_radius=16)

    def hide(self, widget=None, **kwargs):
        browser = self.browser()
        if browser is not None and browser.details_panel is self:
            browser.details_panel = None
        if self.overlay is not None:
            self.overlay.close()
            self.overlay = None


class LocalFileBrowser(FileBrowser):
    # 96 for the preview, 72 for the title and 4-point card margins.
    TILE_ROW_HEIGHT = 176

    def __init__(self, **kwargs):
        self.thumbnails = None
        self._previews_visible = False
        self._preview_update = None
        self._preview_jobs = {}
        self._preview_completed = set()
        self._tile_selecting = False
        self.details_panel = None
        self._tile_previews = {}
        self._mode_anchor = None
        self._restoring_tile_anchor = False
        self._defer_tile_mount = False
        super().__init__(**kwargs)
        self.presentation.style_button = _style_tile_title
        self.presentation.middle_filename = _tile_filename
        self.view_switch = browser_command(icon_button('file_tiles', 'Show tiles', on_press=self.switch_view))

    def _list_selected(self, widget, **kwargs):
        if not self._rendering and not widget.updating:
            from .native.file_shortcuts import focus
            focus(widget)
        super()._list_selected(widget, **kwargs)

    def configure_previews(self, source):
        if self.details_panel is not None:
            self.details_panel.hide()
        previous = self.thumbnails
        if previous is not None and (previous.provider is not source.provider
                                     or previous.password != source.password):
            self.icons.clear()
            self.work.decoded.clear()
        self._reset_previews()
        self.thumbnails = source

    def show_details_panel(self, owner):
        if self.details_panel is not None:
            self.details_panel.hide()
        self.details_panel = FileDetailsPanel(self, owner)
        self.preview_selected_image(self.details_panel)

    def preview_selected_image(self, panel=None):
        """Show the explicit Details preview without starting row decoders."""
        from .browser_preview import DIRECT_IMAGE_SUFFIXES
        from .routes import contains

        source = self.thumbnails
        entry = self.tree.entries.get(self.selected) if self.tree is not None else None
        if (source is None or source.private or entry is None or not source.supports(entry)
                or entry.suffix.lower() not in DIRECT_IMAGE_SUFFIXES):
            return
        epoch = self.epoch

        def publish(data):
            body = self._app.body
            visible = (self.details_panel is panel if panel is not None else
                       body is not None and contains(body, self.info))
            if (self.closed or source is not self.thumbnails or self.selected != entry.identity
                    or self.epoch != epoch or not visible):
                return
            target = panel.preview if panel is not None else self.info
            if not any(isinstance(child, toga.ImageView) for child in target.children):
                target.add(toga.ImageView(toga.Image(src=data), style=Pack(width=160, height=160)))
                if panel is not None and panel.overlay is not None:
                    panel.overlay_height = min(560, panel.overlay_height + 164)
                    panel.overlay.reposition()

        cached = self.icons.get((entry.identity, entry.revision))
        if cached:
            publish(cached)
        else:
            self._spawn(self.work.thumbnail(entry, source.load, publish,
                epoch=epoch, cancelled=self.cancelled))

    def set_previews_visible(self, visible):
        if not visible and self.details_panel is not None:
            self.details_panel.hide()
        if self._previews_visible != visible:
            self._previews_visible = visible
            if visible:
                self._schedule_previews()
            else:
                self._reset_previews()

    def pause_search_work(self):
        self.set_previews_visible(False)
        if self.thumbnails is not None and self.thumbnails.private:
            self._clear_private_previews()
        super().pause_search_work()

    def _clear_private_previews(self):
        self.icons.clear()
        self.work.decoded.clear()
        for row in self._list_thumbnail_rows.values():
            row.thumbnail = False
            row.icon = self.presentation.file_icon(row.folder)
        self._list_thumbnail_rows.clear()
        for box, placeholder in self._tile_previews.values():
            preview = box.children[0]
            if preview is not placeholder:
                preview.image = None
                box.remove(preview)
                box.add(placeholder)

    def _reset_previews(self):
        if self._preview_update is not None:
            self._preview_update.cancel()
            self._preview_update = None
        for cancelled in self._preview_jobs.values():
            cancelled.set()
        self._preview_completed.clear()

    def stop(self):
        if getattr(self, '_file_drag_delegate', None) is not None:
            from .native.file_drag_ios import uninstall
            uninstall(self)
        if getattr(self, '_android_file_drag', None) is not None:
            from .native.file_drag_android import uninstall
            uninstall(self)
        self.set_previews_visible(False)
        self._reset_previews()
        self.thumbnails = self.details = None
        self._mode_anchor = None
        super().stop()

    def mounted_listing(self):
        return next((widget for widget in (self.native_list, self._tile_scroll, self.empty_label)
                     if widget.parent is self.widget), None)

    def _mount_listing(self, view):
        if not (self._defer_tile_mount and view is self._tile_scroll):
            super()._mount_listing(view)

    def render(self):
        from .native.file_shortcuts import focus, focused

        previous = self.mounted_listing()
        transfer = (previous is not None and previous.factory.Button.__module__.startswith('toga_android.')
                    and focused(previous))
        self._reset_previews()
        defer_tiles = (self._restoring_tile_anchor and previous is not self._tile_scroll
                       and type(self._tile_scroll._impl).__module__.startswith('toga_android.'))
        self._defer_tile_mount = defer_tiles
        try:
            super().render()
        finally:
            self._defer_tile_mount = False
        if defer_tiles:
            # Assemble the anchored rows before attaching the scroll view to the
            # Android window. Each row insertion would otherwise refresh it.
            self._mount_listing(self._tile_scroll)
            self.presentation.bind_keyboard(self)
        if transfer:
            target = self.mounted_listing()
            if target is not None and not focused(target):
                focus(target)
        self._schedule_previews()

    def switch_view(self, widget=None, **kwargs):
        (self.show_tiles if self.mode == 'List' else self.show_list)()

    def show_list(self, widget=None, **kwargs):
        self._show_mode('List')

    def show_tiles(self, widget=None, **kwargs):
        self._show_mode('Tiles')

    def _show_mode(self, mode):
        if self.closed or self.mode == mode:
            return
        self.dismiss_item_menu()
        if self.mode == 'List':
            visible = self._visible_rows()
            index = visible[0] if visible else 0
            entries = self._list_entries
        else:
            index = int(self.vertical_position / self.TILE_ROW_HEIGHT) * 2
            entries = self._tile_entries
            if self._mode_anchor is not None and index + 1 < len(entries):
                if entries[index + 1].identity == self._mode_anchor:
                    index += 1
        anchor = entries[index].identity if 0 <= index < len(entries) else None
        self._mode_anchor = anchor if mode == 'Tiles' else None
        self.mode = mode
        self._restoring_tile_anchor = self._mode_anchor is not None
        try:
            self.render()
        finally:
            self._restoring_tile_anchor = False
        icon, label = ('contents', 'Show rows') if mode == 'Tiles' else ('file_tiles', 'Show tiles')
        apply_icon(self.view_switch, icon, label)
        if hasattr(self.view_switch, '_ios_action_item'):
            self._loop.call_soon(self._app.adaptive.render)
        if mode == 'Tiles':
            position = self._tile_anchor_position()
            self._update_tile_window(position)
            impl = self._tile_scroll._impl
            if type(impl).__module__.startswith('toga_iOS.'):
                # The Toga setter animates on iOS. Finish this mode change
                # immediately so a second tap captures the intended tile row.
                from rubicon.objc import CGPoint
                restore = getattr(self, '_tile_restore', None)
                if restore is not None:
                    restore.cancel()
                impl.native.layoutIfNeeded()
                position = min(position, self._tile_scroll.max_vertical_position)
                impl.native.setContentOffset(CGPoint(0, position), animated=False)
                return
        else:
            index = self._list_indices.get(anchor, 0)
            impl = self.native_list._impl
            if type(impl).__module__.endswith('_android'):
                native = impl.native
                native.setSelectionFromTop(index, 0)
                self._schedule_previews()
                return
            position = index * self.native_list.appearance.row_height
        self.vertical_position = position

    def _visible_rows(self):
        impl = self.native_list._impl
        if type(impl).__module__.endswith('_android'):
            first, last = impl.native.getFirstVisiblePosition(), impl.native.getLastVisiblePosition()
            return range(max(0, first), min(len(self._list_entries), last + 1))
        if type(impl).__module__.endswith('_ios'):
            paths = impl.native.indexPathsForVisibleRows
            return sorted(int(path.row) for path in paths) if paths is not None else ()
        return ()

    def _publish_list_rows(self):
        self.native_list.observe_rows = bool(self.thumbnails and self.thumbnails.enabled)
        super()._publish_list_rows()

    def _row_visible(self, row):
        # Native adapters call during binding. Read the finished viewport on the next turn.
        self._schedule_previews()

    def _tile_card(self, entry):
        card = super()._tile_card(entry)
        image_box, button = card.children
        if type(image_box._impl).__module__.startswith('toga_android.'):
            image_box.style.update(direction=ROW, width=96)
            card.remove(image_box)
            card.insert(0, toga.Box(children=[
                toga.Box(style=Pack(flex=1)), image_box, toga.Box(style=Pack(flex=1)),
            ], style=Pack(direction=ROW, height=96, align_items=CENTER)))
        if self.thumbnails is not None and self.thumbnails.supports(entry):
            self._tile_previews[entry.identity] = image_box, image_box.children[0]
        controls = [button]
        if self.on_item_actions is not None:
            name = entry.payload.get('display_name') or PurePosixPath(entry.label).name
            backend = type(button._impl).__module__
            card._selection_display = object()
            circle = card._tile_selection = icon_button('select_item', 'Select ' + name,
                on_press=partial(self._select_pressed, entry))
            surface(circle, background='transparent', foreground='accent', outlined=False)
            button.style.flex = 1
            card.remove(button)
            caption_controls = [circle, button] if self.on_check_entry is not None else [button]
            card._tile_caption = toga.Box(children=caption_controls,
                style=Pack(direction=ROW, height=72, align_items=CENTER))
            card.add(card._tile_caption)
            self._show_tile_selection(entry, card)
            controls.append(circle)
            if self.on_check_entry is None:
                for control in (card.children[0], button):
                    self._attach_tile_hold(control, entry)
        binding = getattr(self._tile_scroll, '_file_key_binding', None)
        if binding is not None and button.factory.Button.__module__.startswith('toga_android.'):
            # All tile controls dispatch to the same browser and transfer
            # focus to the viewport. Reuse its native key listener.
            for control in controls:
                control._impl.native.setOnKeyListener(binding)
                control._file_key_binding = binding
        return card

    def highlight_selection(self):
        super().highlight_selection()
        if self.mode == 'Tiles':
            selecting = self.on_check_entry is not None
            if self._tile_selecting != selecting:
                self._tile_selecting = selecting
                if not getattr(self, '_tile_updating', False) and self._tile_row_views:
                    # A circle changes each caption's geometry. Rebuild only
                    # the recycled viewport and keep its original scroll offset.
                    position = self.vertical_position
                    for row in tuple(self._tile_row_views.values()):
                        self._tile_rows.remove(row)
                    self._tile_row_views.clear()
                    for identity in tuple(self._tile_cards):
                        self._retire_tile(identity)
                    self._tile_range = None
                    self._update_tile_window(position)
                    return
            for entry, card, _, _, _ in self._tile_cards.values():
                if hasattr(card, '_tile_selection'):
                    self._show_tile_selection(entry, card)

    def _show_tile_selection(self, entry, card):
        state = entry.identity in self.checked_entries if self.on_check_entry is not None else None
        if card._selection_display is state:
            return
        card._selection_display = state
        circle = card._tile_selection
        selected_mode = state is not None
        circle.style.update(display='pack' if selected_mode else 'none',
                            visibility='visible' if selected_mode else 'hidden')
        if selected_mode:
            name = entry.payload.get('display_name') or PurePosixPath(entry.label).name
            apply_icon(circle, 'selected_item' if state else 'select_item',
                       ('Deselect ' if state else 'Select ') + name)
        if type(card._impl).__module__.startswith('toga_iOS.'):
            title = card._tile_caption.children[-1]
            controls = (title, circle) if selected_mode else (title,)
            card._impl.native.accessibilityElements = [control._impl.native for control in controls]

    def _attach_tile_hold(self, control, entry):
        backend = type(control._impl).__module__
        if backend.startswith('toga_android.'):
            from .native.file_drag_android import attach_tile_hold
            control._tile_hold = attach_tile_hold(self, control._impl.native, entry)
        elif backend.startswith('toga_iOS.') and isinstance(control, toga.Button):
            from .native.file_drag_ios import attach_accessibility_action

            control._tile_hold = attach_accessibility_action(self, control._impl.native, entry)

    @property
    def can_show_tile_actions(self):
        return (self.mode == 'Tiles' and not self.closed and not self.navigation_busy
                and self.on_check_entry is None and self.on_item_actions is not None)

    async def _select_pressed(self, entry, widget, **kwargs):
        if self.mode == 'Tiles' and widget is self.buttons.get(entry.identity):
            from .native.file_shortcuts import focus
            focus(self._tile_scroll)
        return await super()._select_pressed(entry, widget, **kwargs)

    async def _tile_actions(self, entry, widget=None, **kwargs):
        if not self.can_show_tile_actions or not self._entry_current(entry):
            return
        from .native.file_shortcuts import focus
        focus(self._tile_scroll)
        entry = await self.validate_cached_entry(entry)
        if entry is None or not self._entry_current(entry):
            return
        await self.select(entry)
        if self.can_show_tile_actions and self.selected == entry.identity and self._entry_current(entry):
            self.on_item_actions(entry.payload)

    def _retire_tile(self, identity):
        _, card, *_ = self._tile_cards[identity]
        button, image = self.buttons[identity], card.children[0]
        for control in (image, button):
            if getattr(control, '_tile_hold', None) is None:
                continue
            if type(control._impl).__module__.startswith('toga_android.'):
                control._tile_hold[2]()
                control._impl.native.setOnLongClickListener(None)
                control._impl.native.setOnTouchListener(None)
            else:
                control._impl.native.accessibilityCustomActions = None
            control._tile_hold = None
        target = self._tile_previews.pop(identity, None)
        if target is not None:
            box, placeholder = target
            token = id(box)
            cancelled = self._preview_jobs.get(token)
            if cancelled is not None:
                cancelled.set()
            self._preview_completed.discard(token)
            preview = box.children[0]
            if preview is not placeholder:
                preview.image = None
        super()._retire_tile(identity)

    def _tile_anchor_position(self):
        index = next((i for i, entry in enumerate(self._tile_entries) if entry.identity == self._mode_anchor), 0)
        return (index // 2) * self.TILE_ROW_HEIGHT

    def _update_tile_window(self, position):
        if self._restoring_tile_anchor:
            # The shared renderer starts at zero. Build the destination window
            # immediately while switching from a scrolled list.
            position = self._tile_anchor_position()
        # Card selection repaints the same controls that construction styles.
        # Only apply their final appearance to the native views.
        with batch_surfaces():
            super()._update_tile_window(position)
        self._schedule_previews()

    def _schedule_previews(self, delay=0):
        if (self.closed or not self._previews_visible or self.thumbnails is None
                or not self.thumbnails.enabled):
            return
        when = self._loop.time() + delay
        if self._preview_update is not None:
            if self._preview_update.when() <= when:
                return
            # A native bind should retire recycled rows on the next turn,
            # even if a delayed fallback check is already queued.
            self._preview_update.cancel()
        self._preview_update = self._loop.call_at(when, self._update_previews)

    def _preview_targets(self):
        if self.mode == 'List':
            return {id(row): (row.entry, row) for index in self._visible_rows()
                    if 0 <= index < len(self.native_list.data)
                    and self.thumbnails.supports((row := self.native_list.data[index]).entry)}
        return {id(box): (self._tile_cards[identity][0], (box, placeholder))
                for identity, (box, placeholder) in self._tile_previews.items()}

    def _update_previews(self):
        self._preview_update = None
        source = self.thumbnails
        if self.closed or not self._previews_visible or source is None:
            return
        if not source.can_publish():
            self._reset_previews()
            if source.private:
                self._clear_private_previews()
            return
        targets = self._preview_targets()
        self._preview_completed.intersection_update(targets)
        for token, cancelled in self._preview_jobs.items():
            if token not in targets:
                cancelled.set()
        for token, (entry, target) in targets.items():
            if token in self._preview_completed or token in self._preview_jobs:
                continue
            if self.mode == 'List' and target.thumbnail:
                continue
            key = entry.identity, entry.revision
            if key in self.icons:
                self.icons.move_to_end(key)
                self._publish_preview(target, toga.Image(src=self.icons[key]))
                self._preview_completed.add(token)
            elif len(self._preview_jobs) < 2:
                cancelled = self._preview_jobs[token] = Event()
                self._spawn(self._load_preview(source, entry, target, token, cancelled))
        # Native rows notify entry but don't expose an exit callback. Retire
        # out-of-view work even when a scroll exits into unsupported rows.
        if self._preview_jobs:
            self._schedule_previews(.06)

    async def _load_preview(self, source, entry, target, token, cancelled):
        def publish(data):
            if (not self._previews_visible or source is not self.thumbnails or not source.can_publish()
                    or token not in self._preview_targets()):
                # The shared cache writes before calling publish. Discard a
                # result that left its viewport or lost access during decoding.
                self.icons.pop((entry.identity, entry.revision), None)
                return
            self._publish_preview(target, toga.Image(src=data))
        try:
            await self.work.thumbnail(entry, source.load, publish, epoch=self.epoch, cancelled=cancelled)
        finally:
            self._preview_jobs.pop(token, None)
            if not cancelled.is_set():
                self._preview_completed.add(token)
            self._schedule_previews()

    def _publish_preview(self, target, image):
        if self.mode == 'List':
            self._set_row_thumbnail(target, image)
        else:
            box, placeholder = target
            if box.children[0] is placeholder:
                # The window needs a fallback glyph immediately. Allocate a
                # second native image view only for a successful decode.
                preview = toga.ImageView(image, style=Pack(flex=1, height=96))
                box.clear()
                box.add(preview)
            else:
                box.children[0].image = image
