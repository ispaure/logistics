"""Shared root actions projected into native trailing bars or Android headers."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from .appearance import surface
from .control_icons import icon_button


def prepare(app, view, destination):
    if destination not in ('home', 'files', 'documents'):
        return view
    if not isinstance(view, toga.Box) or getattr(view, '_hub_sections', False):
        original = view
        view = toga.Box(children=[original], style=Pack(direction=COLUMN, flex=1))
        view.content = getattr(original, 'content', original)
    if hasattr(view, '_destination_actions'):
        return view
    # Existing root pages already own different content margins. Cancel that
    # contribution so the action row has one common window-relative inset.
    header = toga.Box(style=Pack(direction=ROW, align_items=CENTER, margin=(
        8 - (view.style.margin_top or 0), 16 - (view.style.margin_right or 0),
        8, 16 - (view.style.margin_left or 0))))
    unlock = surface(icon_button('storage_unlocked', 'Unlock LocalCrypt',
                                on_press=app.show_home_unlock), foreground='accent')
    unlock._toolbar_symbol = 'lock.open'
    unlock._toolbar_group = 'credentials'
    unlock._toolbar_priority = True
    buttons = [unlock]
    if destination == 'documents':
        opener = icon_button('folder_hub', 'Open document', on_press=app.open_hub_file)
        search = icon_button('find', 'Search documents', on_press=app.open_document_search)
        search._toolbar_symbol = 'magnifyingglass'
        view._document_search_button = search
        view._document_search_close = icon_button('close', 'Exit document search', on_press=app.close_document_search)
        new = icon_button('compose', 'New document', on_press=app.new_hub_document)
        opener._toolbar_symbol, new._toolbar_symbol = 'folder', 'plus'
        buttons.extend([opener, new, search])
        from .action_menu import ActionMenu
        more = icon_button('more', 'Document actions')
        more._toolbar_group = 'credentials'
        view._destination_action_menu = ActionMenu(more, app,
            [('Open document', app.open_hub_file), ('New document', app.new_hub_document), ('Search documents', app.open_document_search)], document=False)
    view._destination_actions = (header, buttons)
    def apple_actions():
        actions = selected(app, buttons)
        if destination == 'documents':
            searching = getattr(app, 'documents_search_open', False) or bool(getattr(app, 'documents_query', '').strip())
            view._ios_toolbar_leading = [view._document_search_close] if searching else []
            if searching:
                actions = [button for button in actions if button is not search]
        from .ios_toolbar import vertical_edge, supplemental_fits
        controller = app.native_host.adapter.parent
        budget = app.native_host.adapter.content_controller(destination)
        if destination == 'documents' and vertical_edge(controller) and not supplemental_fits(budget, len(actions)):
            # A folded display can share a short edge with all five tabs. One
            # native menu keeps both commands reachable without covering a tab.
            return [buttons[0], more] if buttons[0] in actions else [more]
        # Horizontal groups run left-to-right; vertical groups run top-to-bottom.
        # Keep Unlock outermost horizontally and first in a vertical action rail.
        if buttons[0] in actions and not vertical_edge(controller):
            actions = [*actions[1:], actions[0]]
        return actions
    view._ios_toolbar_buttons = apple_actions
    view._ios_toolbar_leading = []
    view._ios_toolbar_overflow = False
    # Destination tabs/rail already identify these main pages. Keep their
    # actions without spending title space repeating the selected tab label.
    view._ios_toolbar_title = ''
    view._ios_toolbar_hidden = [header]
    view.insert(0, header)
    refresh(app, view)
    return view


def selected(app, buttons):
    return buttons if app.home_unlock_candidates() else buttons[1:]


def refresh(app, view):
    controls = getattr(view, '_destination_actions', None)
    if controls is None or app.routes.apple:
        return
    header, buttons = controls
    # Unlock is always the outside/rightmost action, independent of the tab.
    actions = selected(app, buttons)
    actions = [*actions[1:], actions[0]] if buttons[0] in actions else actions
    close = getattr(view, '_document_search_close', None)
    searching = close is not None and (getattr(app, 'documents_search_open', False) or bool(getattr(app, 'documents_query', '').strip()))
    if searching:
        actions = [button for button in actions if button is not view._document_search_button]
    leading = [close] if searching else []
    current = [child for child in header.children if isinstance(child, toga.Button)]
    if current == [*leading, *actions]:
        return
    header.clear()
    if actions:
        header.add(*leading, toga.Box(style=Pack(flex=1)), *actions)


def sync_native_host(app, view, destination):
    """Overview actions belong to the whole window, outside nested folder panes.

    A partially folded Workspaces navigation controller can be the lower pane.
    The existing outer navigation controller is the common full-window owner.
    Reader and nested routes continue to use their destination controllers.
    """
    if not app.routes.apple or app.native_host.adapter is None:
        return
    adapter = app.native_host.adapter
    overview = (not app.routes.screens[destination]
                and hasattr(view, '_destination_actions'))
    if overview:
        overview = bool(selected(app, view._destination_actions[1]))
    outer = adapter.outer_navigation
    if bool(outer.isNavigationBarHidden()) == overview:
        outer.setNavigationBarHidden(not overview, animated=False)
