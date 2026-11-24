"""Retained Settings pages and native compact/wide category navigation."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from collections.abc import Mapping

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from .categories import BY_TITLE, display_title
from .titles import show_body_title
from .forms import settings_presentation, fit_section, disclosure, group_rows


class SettingsPages(Mapping):
    """Retain category order while constructing each native page on demand."""
    def __init__(self, factories):
        self.factories, self.built = factories, {}

    def __iter__(self):
        return iter(self.factories)

    def __len__(self):
        return len(self.factories)

    def __contains__(self, title):
        return title in self.factories

    def __getitem__(self, title):
        if title not in self.built:
            self.built[title] = self.factories[title]()
        return self.built[title]



class SettingsNavigation(toga.Box):
    """Window-local categories with native compact routes and retained wide panes."""
    def __init__(self, app, sections):
        super().__init__(style=Pack(direction=COLUMN, flex=1))
        self.owner = app
        from ..appearance import surface, list_button
        def build(value):
            section = value() if callable(value) else value
            surface(section, radius=0, background='settings_background', outlined=False, eink_outlined=False)
            settings_presentation(section)
            return section
        self.sections = SettingsPages({title: lambda value=value: build(value) for title, value in sections.items()})
        self.selected = next(iter(sections))
        self.detail_requested = False
        self.wide = None
        self._reflowing = False
        self._sidebar_position = 0
        self._detail_position = None
        self.options = SettingsPages({title: lambda title=title: toga.ScrollContainer(horizontal=False,
            content=self.sections[title], style=Pack(flex=1)) for title in sections})
        self.buttons = {}
        from ..control_icons import button_icons
        surface(self, radius=0, background='settings_background', outlined=False, eink_outlined=False)
        menu = toga.Box(style=Pack(direction=COLUMN, margin=16))
        rows = []
        for title in sections:
            def choose(widget=None, selected=title, **kwargs):
                self.choose(selected)
            button = list_button(toga.Button(display_title(app, title), on_press=choose, style=Pack(height=52)))
            button._settings_list_styled = True
            button_icons(button, [(BY_TITLE[title].icon, '')])
            disclosure(button)
            button._settings_row = True
            # Match the initial unselected state during detached construction,
            # rather than restyling every native button on the first reflow.
            button._settings_selected = False
            surface(button, radius=8, background='transparent', foreground='text',
                    outlined=False, eink_outlined=False)
            self.buttons[title] = button
            if len(self.buttons) == 1:
                button.style.flex = 1
                self._status_row = toga.Box(children=[button],
                    style=Pack(direction=ROW, align_items=CENTER))
                self._status_row._settings_sync_row = True
                rows.append(self._status_row)
            else:
                rows.append(button)
            end_group = title == ('Features' if 'Features' in sections else 'Appearance' if 'Appearance' in sections else 'App')
            if end_group or title in ('Books & Comics', 'Workspaces', 'Reset', 'About'):
                menu.add(group_rows(rows, icon_inset=True))
                rows = []
        if rows:
            menu.add(group_rows(rows, icon_inset=True))
        self._menu = menu
        # Fit before assigning scroll content: changing each row height after
        # assignment triggers a complete native scroll-content layout per row.
        self.sidebar = toga.ScrollContainer(horizontal=False, style=Pack(flex=1))
        self.detail = surface(toga.Box(style=Pack(direction=COLUMN, flex=1)),
                              radius=0, background='settings_background', outlined=False, eink_outlined=False)
        surface(menu, radius=0, background='settings_background', outlined=False, eink_outlined=False)
        surface(self.sidebar, radius=0, background='settings_background', outlined=False, eink_outlined=False)
        self.panes = toga.Box(children=[self.sidebar], style=Pack(direction=ROW, flex=1))
        self.add(self.panes)

    @staticmethod
    def detach(view):
        if view.parent is not None:
            view.parent.remove(view)

    def choose(self, title):
        if not self.owner.checkpoint():
            return
        self.selected = title
        self.detail_requested = True
        self.update_selection(show_detail=True)
        self.fit_detail(title)
        view = self.options[title]
        on_open = getattr(self.sections[title], '_settings_on_open', None)
        if on_open is not None:
            on_open()
        self.detach(view)
        if self.wide:
            show_body_title(view)
            routes = self.owner.routes
            if routes.screens['settings']:
                routes.trim('settings', 0)
                self._category_on_stack = False
                routes.render('settings')
            for child in list(self.detail.children):
                self.detail.remove(child)
            self.detail.add(view)
        else:
            # The guard above also protects wide layouts; do not checkpoint twice.
            self.owner.show_view(view, checkpoint=False, destination='settings',
                                 route='settings-category', title=display_title(self.owner, title))

    def restore_selection(self, previous):
        screens = self.owner.routes.screens['settings']
        position = previous.sidebar.vertical_position
        previous_view = previous.options.built.get(previous.selected)
        offset = previous_view.vertical_position if previous_view is not None else 0
        previous.detach(previous.sidebar)
        if previous.selected not in self.sections:
            self.owner.routes.trim('settings', 0)
        elif previous.detail_requested:
            self.selected = previous.selected
            self.detail_requested = True
            if offset > 0:
                self._detail_position = (self.selected, offset)
            elif previous._detail_position is not None and previous._detail_position[0] == self.selected:
                self._detail_position = previous._detail_position
            for route, panel, _ in screens:
                if route == 'settings-category':
                    panel.clear()
                    panel.add(self.options[self.selected])
                    self._category_on_stack = True
                    break
        self._sidebar_position = position

    def restore_detail_scroll(self):
        pending = self._detail_position
        if pending is None:
            return
        title, offset = pending
        view = self.options[title]
        native = type(view._impl).__module__.startswith(('toga_iOS.', 'toga_android.'))

        def restore():
            if self._detail_position != pending:
                return
            self._detail_position = None
            if (not self.owner.active_host or self.owner.settings_navigation is not self or self.selected != title
                    or view.parent is None or view.vertical_position > 0):
                return
            target = min(offset, view.max_vertical_position)
            if native:
                from ..reader_lifecycle import restore_scroll
                restore_scroll(view, (0, target))
            else:
                view.vertical_position = target

        if native:
            # Native scroll bounds may still be empty on the first tree update.
            async def after_draw():
                from commonUtils.ui.native.draw_ready import wait_for_draw
                await wait_for_draw(view)
                restore()
            self.owner.loop.create_task(after_draw())
        else:
            restore()

    def update_selection(self, *, show_detail=False):
        from ..appearance import surface
        status = self.owner.settings_status
        if show_detail:
            section = self.sections[self.selected]
            if status.parent is not section:
                self.detach(status)
                section.add(status)
        for title, button in self.buttons.items():
            selected = bool(self.wide and title == self.selected)
            if getattr(button, '_settings_selected', None) == selected:
                continue
            button.style.font_weight = 'bold' if selected else 'normal'
            surface(button, radius=8, background='hover' if selected else 'transparent',
                    foreground='text', outlined=False, eink_outlined=False, eink_selected=selected)
            backend = type(button._impl).__module__
            if backend.startswith('toga_iOS.'):
                button._impl.native.accessibilityTraits = (1 | 4) if selected else 1
            elif backend.startswith('toga_android.'):
                button._impl.native.setSelected(selected)
            button._settings_selected = selected

    def fit_detail(self, title):
        section = self.sections[title]
        if getattr(section, '_settings_fit_width', None) != self.detail_width:
            fit_section(section, self.detail_width)
            section._settings_fit_width = self.detail_width

    def reflow(self):
        if self._reflowing:
            return
        self._reflowing = True
        try:
            self._reflow()
        finally:
            self._reflowing = False

    def _reflow(self):
        from ..fold_layout import division
        from ..pane_layout import panes
        app = self.owner
        width = app.adaptive.content_width('settings', margin=0, full=True)
        screens = app.routes.screens['settings']
        panel = screens[-1][1] if screens else self.panes
        fold = division(app, panel)
        was_wide = self.wide
        if fold is not None and fold.vertical:
            self.wide = min(fold.x, width - fold.x - fold.width) >= 240
        else:
            self.wide = width >= 640 or fold is not None
        if not self.wide:
            fold = None
        active = app.native_host.state.destination == 'settings'
        category_on_top = bool(screens and screens[-1][0] == 'settings-category')
        if active and not was_wide and not screens and getattr(self, '_category_on_stack', False):
            self.detail_requested = False
        sidebar_width = fold.x if fold is not None and fold.vertical else min(320, max(240, width * .32))
        allocation = panes(width, panel.layout.content_height or 1, fold=fold, browser_priority=True)
        stacked = fold is not None and not fold.vertical
        self.panes.style.direction = COLUMN if stacked else ROW
        gap = fold.width if fold is not None and fold.vertical else 0
        self.detail.style.margin_left = gap
        self.detail.style.margin_top = fold.height if stacked else 0
        for pane, extent in ((self.sidebar, allocation.leading), (self.detail, allocation.trailing)):
            del pane.style.height
            pane.style.flex = 0 if stacked else (1 if pane is self.detail else 0)
            if stacked:
                pane.style.height = extent
        detail_width = width if stacked else (width - sidebar_width - self.detail.style.margin_left if self.wide else width)
        self.detail_width = detail_width
        menu_width = sidebar_width if self.wide and not stacked else width
        # The category menu is static. Avoid native text reads, sizing and
        # drawable updates for every row on each tab/resize callback.
        if getattr(self, '_menu_fit_width', None) != menu_width:
            fit_section(self._menu, menu_width)
            self._menu_fit_width = menu_width
        if self.sidebar.content is None:
            self.sidebar.content = self._menu
        if self.wide:
            if not self.detail_requested:
                self.selected = next(iter(self.sections))
            self.sidebar.style.flex = 0
            # A partially folded Duo uses the physical seam, including rail/safe areas.
            self.sidebar.style.width = width if stacked else sidebar_width
            if category_on_top and active:
                self.detach(self.options[self.selected])
                app.routes.trim('settings', len(screens) - 1)
                app.routes.render('settings')
            if self.detail.parent is None:
                self.panes.add(self.detail)
            # A nested page can still own the compact category beneath it. Wait
            # for native Back before moving that retained category to the root.
            if not any(screen[0] == 'settings-category' for screen in screens):
                view = self.options[self.selected]
                if view.parent is not self.detail:
                    show_body_title(view)
                    self.detach(view)
                    for child in list(self.detail.children):
                        self.detail.remove(child)
                    self.detail.add(view)
        else:
            self.sidebar.style.flex = 1
            from toga.style.pack import NONE
            if self.sidebar.style.width != NONE:
                del self.sidebar.style.width
            if self.detail.parent is self.panes:
                self.panes.remove(self.detail)
            if active and not screens and self.detail_requested:
                self.choose(self.selected)
        panel = screens[-1][1] if self.wide and screens else self.panes
        if self.sidebar.parent is not panel:
            if not self._sidebar_position:
                self._sidebar_position = self.sidebar.vertical_position
            old_panel = self.sidebar.parent
            self.detach(self.sidebar)
            if old_panel is not None and old_panel is not self.panes:
                old_panel.style.direction = COLUMN
            panel.insert(0, self.sidebar)
        if self._sidebar_position:
            def restore():
                if self.sidebar.parent is panel and self._sidebar_position:
                    self.sidebar.vertical_position = self._sidebar_position
                    self._sidebar_position = 0
            app.loop.call_soon(restore)
        self.sidebar.style.margin_right = gap if panel is not self.panes else 0
        self.sidebar.style.margin_bottom = fold.height if stacked and panel is not self.panes else 0
        if screens:
            current = screens[-1][1]
            current.style.direction = self.panes.style.direction if self.wide else COLUMN
            view = current.children[-1]
            content = view.content if isinstance(view, toga.ScrollContainer) else view
            if isinstance(content, toga.Box) and not category_on_top:
                layout = (id(view), detail_width)
                if getattr(current, '_settings_route_layout', None) != layout:
                    fit_section(content, detail_width)
                    current._settings_route_layout = layout
        self._category_on_stack = any(screen[0] == 'settings-category' for screen in screens)
        self.update_selection(show_detail=self.wide or category_on_top)
        if self.wide or category_on_top:
            self.fit_detail(self.selected)
