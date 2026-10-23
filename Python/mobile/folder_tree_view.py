"""Retained Workspaces tree controls, independent of discovery and navigation state.

One view owns one source tab's rows and menus. Render inputs describe the current
visible folders; callbacks resolve host actions only when the user invokes them.
"""
from dataclasses import dataclass
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from .appearance import accessible_name, list_button
from .control_icons import icon_button
from .folder_hub import folder_row_presentation, folder_tree
from .folder_hub_style import (
    surface, compact_icon, folder_row, folder_name, ROW_HEIGHT, ROW_GAP,
    ENTRY_ICON_SLOT, ENTRY_ICON_SIZE, tree_anchor, tree_guide, TREE_LABEL_GAP,
    align_group_label,
)
from .ui_metrics import TOUCH_TARGET, BODY_TEXT, toga_font_size


@dataclass
class _FolderRow:
    name: str | None
    row: toga.Box
    presentation: tuple | None = None
    group: toga.Label | None = None
    child_box: toga.Box | None = None
    divider: toga.Box | None = None
    geometry: tuple | None = None
    indicator: toga.Button | None = None
    button: toga.Button | None = None
    menu: toga.Button | None = None
    commands: object = None
    child_content: toga.Box | None = None
    guide: toga.Box | None = None


def _sync_children(parent, children):
    # Native remove/add triggers layout. Touch only changed positions.
    for child in list(parent.children):
        if child not in children:
            parent.remove(child)
    for index, child in enumerate(children):
        if index < len(parent.children) and parent.children[index] is child:
            continue
        if child.parent is not None:
            child.parent.remove(child)
        parent.insert(index, child)


def _divider():
    return surface(toga.Box(style=Pack(height=1, margin_left=34)),
                   radius=0, background='transparent', outlined=False)


def _branch_height(branch):
    return sum(ROW_HEIGHT + ROW_GAP
               + (_branch_height(node['children']) if node['children'] else 0)
               for node in branch.values()) + max(0, len(branch) - 1)


def _child_midpoints(branch):
    offset = 0
    for _, node in sorted(branch.items(), key=lambda item: item[0].casefold()):
        yield offset + ROW_HEIGHT / 2
        offset += ROW_HEIGHT + ROW_GAP + 1
        if node['children']:
            offset += _branch_height(node['children'])


class FolderTreeView:
    """Own native row identity and menu retirement for one retained source tab."""
    def __init__(self, *, browse, choose, actions, invoke, native_context):
        self.browse_folder, self.choose_folder = browse, choose
        self.load_actions, self.invoke, self.native_context = actions, invoke, native_context
        self.content = toga.Box(style=Pack(direction=COLUMN))
        self.nodes, self.panels, self.extras = {}, {}, {}
        self.browse, self.buttons, self.tree_buttons = {}, {}, {}

    def render(self, visible, source, loaded_remotes, crypt_remotes):
        """Reconcile this source snapshot; unchanged rows keep native identity."""
        nodes, panels, buttons, tree_buttons = {}, {}, {}, {}

        def add_branch(branch, parent, ancestors=()):
            children = []
            for index, (title, node) in enumerate(sorted(branch.items(), key=lambda item: item[0].casefold())):
                path = (*ancestors, title)
                name = node['names'][0] if node['names'] else None
                projected = (folder_row_presentation(title, visible[name], source,
                    loaded_remotes, crypt_remotes) if name is not None else None)
                record = self._row_for(path, title, name, projected)
                nodes[path] = record
                if name is not None:
                    buttons[name] = record.button
                else:
                    tree_buttons[path] = record.group
                children.append(record.row)
                if node['children']:
                    if record.child_box is None:
                        record.child_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
                        record.child_box = toga.Box(style=Pack(direction=ROW))
                    add_branch(node['children'], record.child_content, path)
                    geometry = (_branch_height(node['children']), tuple(_child_midpoints(node['children'])),
                                tree_anchor(record.group))
                    if record.geometry != geometry:
                        record.guide = tree_guide(*geometry)
                        record.geometry = geometry
                    _sync_children(record.child_box, [record.guide, record.child_content])
                    children.append(record.child_box)
                elif record.child_box is not None:
                    # Drop removed descendants even when their parent remains.
                    _sync_children(record.child_content, [])
                if index < len(branch) - 1:
                    if record.divider is None:
                        record.divider = _divider()
                    children.append(record.divider)
            _sync_children(parent, children)

        content = []
        folders = {name: entry for name, entry in visible.items() if not entry.get('browser_root')}
        for title, node in sorted(folder_tree(folders).items(), key=lambda item: item[0].casefold()):
            panel = self.panels.get(title)
            if panel is None:
                branch_content = toga.Box(style=Pack(direction=COLUMN))
                panel = surface(toga.Box(children=[branch_content], style=Pack(direction=COLUMN)),
                                radius=0, background='transparent', outlined=False)
                panel.style.margin_bottom = 12
            add_branch({title: node}, panel.children[0])
            panels[title] = panel
            content.append(panel)
        if not folders:
            if 'empty' not in self.extras:
                self.extras['empty'] = toga.Label('No folders available for this source.')
            content.append(self.extras['empty'])
        browse = {}
        for name, entry in visible.items():
            if entry.get('browser_root'):
                button = self.browse.get(name)
                if button is None:
                    async def browse_all(widget=None, selected=name, **kwargs):
                        return await self.browse_folder(selected)
                    button = list_button(toga.Button('Browse All Files', on_press=browse_all,
                        style=Pack(height=ROW_HEIGHT, margin_top=12)))
                browse[name] = buttons[name] = button
                content.append(button)
        if 'legend' not in self.extras:
            legend = toga.Box(style=Pack(direction=ROW, align_items=CENTER, margin_top=4))
            for label, icon, color in (('Locked', 'folder_locked', 'folder_locked'),
                                       ('Unlocked', 'folder_unlocked', 'folder_unlocked')):
                mark = icon_button(icon, label + ' folder')
                compact_icon(mark, width=28, height=32, size=22, background='window', foreground=color)
                legend.add(mark)
                legend.add(surface(toga.Label(label, style=Pack(font_size=11, margin_right=16)),
                                   background='window', foreground='muted', outlined=False))
            self.extras['legend'] = legend
        content.append(self.extras['legend'])
        _sync_children(self.content, content)
        for path, old in self.nodes.items():
            if nodes.get(path) is not old and getattr(old, 'commands', None) is not None:
                old.commands.dispose()
        self.nodes, self.panels, self.browse = nodes, panels, browse
        self.buttons, self.tree_buttons = buttons, tree_buttons

    def _row_for(self, path, title, name, projected):
        """Reuse a path only while it still represents the same selectable folder."""
        if projected is not None:
            icon, description, state = projected.icon, projected.description, projected.state
            presentation = (projected.title, icon, description)
        record = self.nodes.get(path)
        if record is None or record.name != name:
            row = toga.Box(style=Pack(direction=ROW, align_items=CENTER,
                                     height=ROW_HEIGHT, margin_bottom=ROW_GAP))
            record = _FolderRow(name=name, row=row)
            if name is not None:
                async def select(widget=None, selected=name, **kwargs):
                    return await self.browse_folder(selected)
                record.indicator = icon_button(icon, name + ', ' + description, on_press=select)
                record.button = folder_name(list_button(toga.Button(title, on_press=select,
                    style=Pack(height=ROW_HEIGHT, flex=1))))
                def options(widget=None, selected=name, **kwargs):
                    self.choose_folder(selected)
                record.menu = icon_button('more', 'Workspace actions for ' + name, on_press=options)
                compact_icon(record.menu, width=TOUCH_TARGET, size=18)
                from .action_menu import WorkspaceMenu
                record.commands = WorkspaceMenu(record.menu,
                    lambda selected=name: self.load_actions(selected),
                    invoke=self.invoke,
                    context=self.native_context,
                    fallback=lambda selected=name: self.choose_folder(selected))
                row.add(record.indicator, record.button, record.menu)
                folder_row(row)
            else:
                record.group = surface(toga.Label(title,
                    style=Pack(height=20, margin_top=14, margin_bottom=14, font_size=toga_font_size(BODY_TEXT),
                               margin_left=TREE_LABEL_GAP if len(path) > 1 else 0,
                               font_weight='bold', flex=1)), radius=0,
                    background='transparent', foreground='text', outlined=False)
                align_group_label(record.group)
                accessible_name(record.group, title + ', group')
                row.add(record.group)
        if name is not None:
            if record.presentation != presentation:
                if record.indicator.control_icon != icon:
                    from .control_icons import apply_icon
                    apply_icon(record.indicator, icon, name + ', ' + description, preserve_layout=True)
                if record.button.text != title:
                    record.button.text = title
                accessible_name(record.indicator, name + ', ' + description)
                accessible_name(record.button, name + ', ' + description)
                color = 'folder_' + state if state else 'folder'
                if record.presentation is None:
                    compact_icon(record.indicator, width=ENTRY_ICON_SLOT, size=ENTRY_ICON_SIZE, foreground=color)
                else:
                    surface(record.indicator, radius=0, background='transparent', foreground=color, outlined=False)
                record.presentation = presentation
        return record
