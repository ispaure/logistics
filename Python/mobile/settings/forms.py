"""Compact preference rows and offline installed-build information."""
import json
from pathlib import Path
import sys
from collections.abc import Mapping

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from services.build_version import BuildVersion, installed_build


from commonUtils.ui.native import forms as _forms
from commonUtils.ui.native.forms import wrap_text, FittedLabel as SettingsLabel


def fit_text(control, width):
    from ..appearance import list_button
    return _forms.fit_text(control, width, style_button=list_button)


def _label_reserve(section):
    if getattr(section, '_connection_switch_row', False):
        return 72
    if getattr(section, '_settings_switch_row', False):
        switch = section.children[1]
        return max(64, getattr(switch.intrinsic.width, 'value', switch.intrinsic.width) or 0)
    return None


def fit_section(section, width):
    return _forms.fit_section(section, width, fit=fit_text, reserved_width=_label_reserve)


def disclosure(button):
    from ..appearance import apple_color
    return _forms.disclosure(button, apple_color=apple_color)


def group_rows(rows, *, icon_inset=False):
    from ..appearance import surface
    return _forms.group_rows(rows, surface=surface, icon_inset=icon_inset,
                             background='settings_group', separator='settings_separator')


def settings_presentation(section):
    """Group related native controls; keep explanations outside the surface."""
    from ..appearance import surface
    children = list(section.children)
    for child in children:
        section.remove(child)
    rows = []
    def flush():
        if rows:
            section.add(group_rows(rows))
            rows.clear()
    consumed = set()
    for index, child in enumerate(children):
        if child in consumed:
            continue
        if isinstance(child, toga.Button):
            child.style.height = 52
            child._settings_row = True
            surface(child, radius=0, background='transparent', foreground='accent',
                    outlined=False, eink_outlined=False)
            if child.text.endswith('…') or child.text == 'Mobile documentation':
                disclosure(child)
            rows.append(child)
        elif getattr(child, '_settings_switch_row', False):
            label, switch = child.children
            surface(switch, radius=0, background='transparent', outlined=False, eink_outlined=False)
            surface(label, radius=0, background='transparent', foreground='text', outlined=False, eink_outlined=False)
            child.style.margin_bottom = 0
            rows.append(child)
            flush()
            section.children[-1].style.margin_bottom = 6
            note = child._settings_note
            note.style.margin_left = note.style.margin_right = 16
            note.style.margin_bottom = 20
            section.add(note)
        elif isinstance(child, toga.Selection):
            surface(child, radius=0, background='transparent', outlined=False, eink_outlined=False)
            child.style.margin_top = 4
            child.style.margin_bottom = 8
            rows.append(child)
        elif isinstance(child, toga.Label):
            primary = child.style.font_weight == 'bold' or (index + 1 < len(children) and isinstance(children[index + 1], toga.Selection))
            surface(child, radius=0, background='transparent', foreground='text' if primary else 'muted',
                    outlined=False, eink_outlined=False)
            if primary and child.style.font_weight != 'bold':
                child.style.margin_top = 12
                choice = children[index + 1]
                surface(choice, radius=0, background='transparent', outlined=False, eink_outlined=False)
                consumed.add(choice)
                choice.style.margin_top = 4
                choice.style.margin_bottom = 12
                rows.append(toga.Box(children=[child, choice], style=Pack(direction=COLUMN)))
            else:
                flush()
                if child.style.font_weight != 'bold':
                    child.style.font_size = 13
                    if section.children and getattr(section.children[-1], '_settings_group', False):
                        section.children[-1].style.margin_bottom = 6
                child.style.margin_left = child.style.margin_right = 12
                child.style.margin_bottom = 12
                section.add(child)
        elif isinstance(child, toga.Box):
            flush()
            settings_presentation(child)
            section.add(child)
    flush()


def connection_note(text):
    from ..appearance import surface
    return surface(SettingsLabel(text, style=Pack(font_size=12, margin_bottom=12)),
                   radius=0, background='transparent', foreground='muted', outlined=False, eink_outlined=False)


def connection_heading(text):
    from ..appearance import surface
    return surface(SettingsLabel(text, style=Pack(font_size=12, font_weight='bold', margin_top=16, margin_bottom=8)),
                   radius=0, background='transparent', foreground='muted', outlined=False, eink_outlined=False)


def connection_field(title, control):
    label = connection_note(title)
    label.style.margin_bottom = 4
    return toga.Box(children=[label, control], style=Pack(direction=COLUMN, margin_top=8, margin_bottom=8))


def connection_group(rows):
    from ..appearance import surface, list_button, accessible_name
    result = []
    for row in rows:
        if isinstance(row, toga.Button):
            list_button(row)
            surface(row, radius=0, background='transparent', foreground='accent', outlined=False, eink_outlined=False)
        if isinstance(row, toga.Switch):
            title, row.text = row.text, ''
            accessible_name(row, title)
            row.style.flex = 0
            row.style.width = 64
            row = toga.Box(children=[SettingsLabel(title, style=Pack(flex=1)), row],
                           style=Pack(direction=ROW, align_items=CENTER))
            row._connection_switch_row = True
        result.append(row)
    return group_rows(result)


def connection_disclosure(title, children):
    """Retain form values while advanced controls are out of the layout."""
    from ..appearance import surface, list_button
    def changed(box):
        parent = box.parent
        while parent is not None:
            if isinstance(parent, ConnectionSettingsPage):
                parent.reflow()
                break
            parent = parent.parent
    def style(button):
        return surface(list_button(button), radius=0, background='transparent',
                       foreground='accent', outlined=False, eink_outlined=False)
    return _forms.collapsible(title, children, style_button=style, changed=changed)


class ConnectionSettingsPage(toga.ScrollContainer):
    """Grouped connection forms share Settings colours and fit native phone labels."""
    def __init__(self, app, title, subtitle, children):
        from ..appearance import surface
        self.owner = app
        content = toga.Box(children=[SettingsLabel(title, style=Pack(font_size=27, font_weight='bold', margin_bottom=8)),
                                     connection_note(subtitle), *children],
                           style=Pack(direction=COLUMN, margin=20))
        surface(content, radius=0, background='settings_background', outlined=False, eink_outlined=False)
        super().__init__(horizontal=False, content=content, style=Pack(flex=1))
        self.reflow()

    def reflow(self):
        fit_section(self.content, self.owner.adaptive.content_width('settings', margin=0))


def switch_row(app, title, switch, explanation):
    # Keep the switch's native accessible label with a separate visible title.
    switch.text = ''
    switch.style.flex = 0
    switch.style.width = 64
    from ..appearance import accessible_name
    accessible_name(switch, title)
    row = toga.Box(children=[
        SettingsLabel(title, style=Pack(flex=1)),
        switch,
    ], style=Pack(direction=ROW, align_items=CENTER, margin_bottom=8))
    row._settings_switch_row = True
    row._settings_note = connection_note(explanation)
    row._settings_note.style.font_size = 13
    return row
