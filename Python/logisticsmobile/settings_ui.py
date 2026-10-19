"""Compact preference rows and offline installed-build information."""
import json
from pathlib import Path
import sys

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from services.build_version import BuildVersion, installed_build


def wrap_text(text, width, measure):
    """Insert explicit line breaks: Toga labels do not wrap on iOS."""
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split():
            candidate = (line + ' ' + word).lstrip()
            if measure(candidate) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
            line = ''
            # Build identifiers must also fit the pane.
            for char in word:
                if line and measure(line + char) > width:
                    lines.append(line)
                    line = ''
                line += char
        lines.append(line)
    return '\n'.join(lines)


def fit_text(control, width):
    """Fit retained text to its pane using the actual native font on Apple."""
    control._settings_available_width = width
    previous = getattr(control, '_settings_rendered_text', None)
    if control.text != previous:
        control._settings_source_text = control.text
    source = control._settings_source_text
    button = isinstance(control, toga.Button)
    width = max(24, width - (24 if button else 0)
                - (24 if getattr(control, '_settings_disclosure', False) else 0)
                - (32 if getattr(control, 'leading_icons', ()) else 0))
    size = control.style.font_size
    if size is None or size <= 0:
        size = 17
    line_height = size * 1.4
    def measure(text):
        return len(text) * size * .65
    if type(control._impl).__module__.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass, CGSize
        native = control._impl.native
        font = native.titleLabel.font if button else native.font
        ruler = ObjCClass('UILabel').new()
        ruler.font = font
        def measure(text):
            ruler.text = text
            return float(ruler.sizeThatFits(CGSize(100000, 100000)).width)
        line_height = float(font.lineHeight)
    key = (source, width, line_height)
    if getattr(control, '_settings_fit_key', None) == key and control.text == previous:
        return
    control._settings_fit_key = key
    rendered = wrap_text(source, width, measure)
    if rendered != control.text:
        # Toga's public Button setter discards everything after a newline.
        # Apply presentation text without replacing a SettingsLabel's source.
        control._impl.set_text(rendered)
        control.refresh()
    control._settings_rendered_text = rendered
    if button:
        from .appearance import list_button
        list_button(control)
        control.style.height = max(52 if getattr(control, '_settings_row', False) else 48, int(line_height * len(rendered.split('\n')) + 20))
        if type(control._impl).__module__.startswith('toga_iOS.'):
            control._impl.native.titleLabel.numberOfLines = len(rendered.split('\n'))
            control._impl.native.accessibilityLabel = source
        elif type(control._impl).__module__.startswith('toga_android.'):
            control._impl.native.setSingleLine(False)
            control._impl.native.setMaxLines(len(rendered.split('\n')))


def fit_section(section, width):
    """Keep each category within its scroll viewport, including switch rows."""
    width = max(24, width - section.style.margin_left - section.style.margin_right)
    if getattr(section, '_connection_switch_row', False):
        fit_text(section.children[0], max(24, width - 72))
        return
    if getattr(section, '_settings_switch_row', False):
        label, info, switch = section.children
        # UISwitch has a fixed native width; leave its full target beside help.
        switch_width = max(64, getattr(switch.intrinsic.width, 'value', switch.intrinsic.width) or 0)
        fit_text(label, max(24, width - 48 - switch_width))
        return
    for child in section.children:
        if isinstance(child, (toga.Label, toga.Button)):
            fit_text(child, width)
        elif isinstance(child, toga.Box):
            fit_section(child, width)


def disclosure(button):
    """A trailing accessory inside the native button's full accessible hit target."""
    button._settings_disclosure = True
    backend = type(button._impl).__module__
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        native = button._impl.native
        image = ObjCClass('UIImage').systemImageNamed('chevron.right')
        accessory = ObjCClass('UIImageView').alloc().initWithImage(image)
        accessory.translatesAutoresizingMaskIntoConstraints = False
        from .appearance import apple_color
        accessory.tintColor = apple_color('muted')
        accessory.isAccessibilityElement = False
        native.addSubview(accessory)
        accessory.trailingAnchor.constraintEqualToAnchor(native.trailingAnchor, constant=-8).active = True
        accessory.centerYAnchor.constraintEqualToAnchor(native.centerYAnchor).active = True
        accessory.widthAnchor.constraintEqualToConstant(10).active = True
        accessory.heightAnchor.constraintEqualToConstant(16).active = True
    elif backend.startswith('toga_android.'):
        from android.graphics import Path, Paint
        from android.graphics.drawable import ShapeDrawable
        from android.graphics.drawable.shapes import PathShape
        path = Path()
        path.moveTo(8, 5)
        path.lineTo(15, 12)
        path.lineTo(8, 19)
        arrow = ShapeDrawable(PathShape(path, 24, 24))
        arrow.getPaint().setStyle(Paint.Style.STROKE)
        arrow.getPaint().setStrokeWidth(1.8)
        arrow.getPaint().setAntiAlias(True)
        native = button._impl.native
        size = button._impl.scale_in(24)
        arrow.setBounds(0, 0, size, size)
        # State-aware tint follows the title, including Android E Ink selection.
        arrow.setTintList(native.getTextColors())
        button._impl._settings_accessory = arrow
        native.setCompoundDrawablesRelative(getattr(button._impl, '_control_drawable', None), None, arrow, None)
    return button


def group_rows(rows, *, icon_inset=False):
    """One shared surface with inset separators, never a box per preference."""
    from .appearance import surface
    group = surface(toga.Box(style=Pack(direction=COLUMN, margin_bottom=20)),
                    radius=16, background='settings_group', outlined=False)
    group._settings_group = True
    for index, row in enumerate(rows):
        if index:
            group.add(surface(toga.Box(style=Pack(height=1, margin_left=48 if icon_inset else 16,
                                                 margin_right=16)), radius=0,
                              background='settings_separator', outlined=False, eink_outlined=False))
        row.style.margin_left = 12
        row.style.margin_right = 12
        row.style.margin_top = 4 if index == 0 else 0
        row.style.margin_bottom = 4 if index == len(rows) - 1 else 0
        group.add(row)
    return group


def settings_presentation(section):
    """Group related native controls; keep explanations outside the surface."""
    from .appearance import surface
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
            label, info, switch = child.children
            surface(label, radius=0, background='transparent', foreground='text', outlined=False, eink_outlined=False)
            surface(info, radius=0, background='transparent', foreground='accent', outlined=False, eink_outlined=False)
            child.style.margin_bottom = 0
            rows.append(child)
        elif isinstance(child, toga.Selection):
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
                consumed.add(choice)
                choice.style.margin_top = 4
                choice.style.margin_bottom = 12
                rows.append(toga.Box(children=[child, choice], style=Pack(direction=COLUMN)))
            else:
                flush()
                child.style.margin_left = child.style.margin_right = 12
                child.style.margin_bottom = 12
                section.add(child)
        elif isinstance(child, toga.Box):
            flush()
            settings_presentation(child)
            section.add(child)
    flush()


class SettingsLabel(toga.Label):
    """Refit asynchronous status messages as soon as their text changes."""
    @toga.Label.text.setter
    def text(self, value):
        toga.Label.text.fset(self, value)
        width = getattr(self, '_settings_available_width', None)
        if width is not None:
            fit_text(self, width)


def connection_note(text):
    from .appearance import surface
    return surface(SettingsLabel(text, style=Pack(font_size=12, margin_bottom=12)),
                   radius=0, background='transparent', foreground='muted', outlined=False, eink_outlined=False)


def connection_heading(text):
    from .appearance import surface
    return surface(SettingsLabel(text, style=Pack(font_size=12, font_weight='bold', margin_top=16, margin_bottom=8)),
                   radius=0, background='transparent', foreground='muted', outlined=False, eink_outlined=False)


def connection_field(title, control):
    label = connection_note(title)
    label.style.margin_bottom = 4
    return toga.Box(children=[label, control], style=Pack(direction=COLUMN, margin_top=8, margin_bottom=8))


def connection_group(rows):
    from .appearance import surface, list_button, accessible_name
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
    from .appearance import surface, list_button
    body = toga.Box(children=children, style=Pack(direction=COLUMN))
    box = toga.Box(style=Pack(direction=COLUMN))
    def toggle(widget=None, **kwargs):
        if body.parent is None:
            box.add(body)
            button.text = title + ' −'
        else:
            box.remove(body)
            button.text = title + ' +'
        parent = box.parent
        while parent is not None:
            if isinstance(parent, ConnectionSettingsPage):
                parent.reflow()
                break
            parent = parent.parent
    button = list_button(toga.Button(title + ' +', on_press=toggle, style=Pack(height=48)))
    surface(button, radius=0, background='transparent', foreground='accent', outlined=False, eink_outlined=False)
    box.add(button)
    return box, button


class ConnectionSettingsPage(toga.ScrollContainer):
    """Grouped connection forms share Settings colours and fit native phone labels."""
    def __init__(self, app, title, subtitle, children):
        from .appearance import surface
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
    async def explain(widget, **kwargs):
        await app.main_window.dialog(toga.InfoDialog(title, explanation))

    # Keep the switch's native accessible label, while drawing the visible label
    # before the help button. Both controls retain a full touch target.
    switch.text = ''
    switch.style.flex = 0
    info = toga.Button('ⓘ', on_press=explain, style=Pack(width=48, height=48))
    for control, label in ((switch, title), (info, 'About ' + title)):
        backend = type(control._impl).__module__
        if backend.startswith('toga_iOS.'):
            control._impl.native.accessibilityLabel = label
        elif backend.startswith('toga_android.'):
            control._impl.native.setContentDescription(label)
    row = toga.Box(children=[
        toga.Label(title, style=Pack(flex=1)),
        info,
        switch,
    ], style=Pack(direction=ROW, align_items=CENTER, margin_bottom=8))
    row._settings_switch_row = True
    return row


def build_information(version, path=None):
    """Use the staged snapshot on devices; Git is only a source-checkout fallback."""
    path = Path(path) if path is not None else Path(__file__).with_name('source.json')
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
        identity = BuildVersion(version or 'Development build', manifest['logistics_commit'],
                                manifest.get('logistics_committed_at', ''),
                                manifest.get('dirty', False))
        snapshot = manifest.get('source_sha256', '')
    except (OSError, ValueError, KeyError, TypeError):
        identity = installed_build()
        if version:
            identity = BuildVersion(version, identity.revision, identity.committed_at, identity.modified)
        snapshot = ''
    platform = {'ios': 'iOS / iPadOS', 'android': 'Android'}.get(sys.platform, sys.platform)
    return '\n'.join(filter(None, (identity.label, 'Platform: ' + platform,
                                   'Source: ' + snapshot[:12] if snapshot else '')))


def speech_voice_setting(app):
    """Load offline voice names on demand, without retaining a speech engine."""
    import asyncio
    from features.books.mobile.speech_native import NativeSpeech
    system = 'System default'
    saved = app.preferences.values['speech_voice']
    choice = toga.Selection(items=[system] + ([saved] if saved else []),
                            value=saved or system, style=Pack(height=48))
    status = SettingsLabel('Uses an installed offline system voice.', style=Pack(font_size=12))

    def save(widget, **kwargs):
        try:
            app.preferences.save(speech_voice='' if widget.value == system else widget.value)
            status.text = 'Read-aloud voice saved on this device.'
        except (OSError, ValueError) as error:
            status.text = str(error)

    choice.on_change = save

    async def load(widget, **kwargs):
        widget.enabled = False
        engine = None
        try:
            engine = NativeSpeech(app.loop)
            for _ in range(150):
                if engine.ready or engine.error:
                    break
                await asyncio.sleep(.1)
            if not engine.ready:
                status.text = engine.error or 'Speech engine did not start.'
                return
            selected = app.preferences.values['speech_voice']
            choice.on_change = None
            choice.items = [system, *sorted(engine.voices)]
            picker = getattr(choice._impl, 'native_picker', None)
            if picker is not None:
                picker.reloadAllComponents()
            choice.value = selected if selected in engine.voices else system
            status.text = ('Saved voice unavailable; using the system default.' if selected and selected not in engine.voices
                           else 'Choose an installed offline voice. Saved immediately.')
        finally:
            choice.on_change = save
            if engine is not None:
                engine.close()
            widget.enabled = True

    app.speech_voice_choice = choice
    return toga.Box(children=[toga.Label('Read-aloud voice'), choice,
        toga.Button('Load installed voices', on_press=load, style=Pack(height=48)), status],
        style=Pack(direction=COLUMN))


class SettingsNavigation(toga.Box):
    """Window-local categories with native compact routes and retained wide panes."""
    def __init__(self, app, sections):
        super().__init__(style=Pack(direction=ROW, flex=1))
        self.owner = app
        self.sections = sections
        from .appearance import surface, list_button
        for section in sections.values():
            surface(section, radius=0, background='settings_background', outlined=False, eink_outlined=False)
            settings_presentation(section)
        self.selected = next(iter(sections))
        self.wide = None
        self._reflowing = False
        self.options = {title: toga.ScrollContainer(horizontal=False, content=section,
                       style=Pack(flex=1)) for title, section in sections.items()}
        self.buttons = {}
        from .control_icons import button_icons
        surface(self, radius=0, background='settings_background', outlined=False, eink_outlined=False)
        menu = toga.Box(style=Pack(direction=COLUMN, margin=16))
        menu.add(surface(toga.Label('Settings', style=Pack(font_size=28, font_weight='bold', margin_bottom=24)),
                         radius=0, background='transparent', foreground='text', outlined=False, eink_outlined=False))
        icons = {'App': 'preferences', 'Appearance': 'appearance', 'Read aloud': 'speaker',
                 'Text & Markdown': 'edit', 'Books & Comics': 'books', 'LM Chat': 'chat',
                 'Workspaces': 'folder', 'Reset': 'preferences', 'Help': 'help', 'About': 'info'}
        rows = []
        for title in sections:
            def choose(widget=None, selected=title, **kwargs):
                self.choose(selected)
            button = list_button(toga.Button(title, on_press=choose, style=Pack(height=52)))
            button_icons(button, [(icons[title], '')])
            disclosure(button)
            button._settings_row = True
            self.buttons[title] = button
            rows.append(button)
            end_group = title == ('Appearance' if 'Appearance' in sections else 'App')
            if end_group or title in ('Books & Comics', 'Workspaces', 'Reset', 'About'):
                menu.add(group_rows(rows, icon_inset=True))
                rows = []
        if rows:
            menu.add(group_rows(rows, icon_inset=True))
        self.sidebar = toga.ScrollContainer(horizontal=False, content=menu, style=Pack(flex=1))
        self.detail = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self.add(self.sidebar)

    @staticmethod
    def detach(view):
        if view.parent is not None:
            view.parent.remove(view)

    def choose(self, title):
        if not self.owner.checkpoint():
            return
        self.selected = title
        self.update_selection()
        view = self.options[title]
        self.detach(view)
        if self.wide:
            for child in list(self.detail.children):
                self.detail.remove(child)
            self.detail.add(view)
        else:
            self.owner.show_view(view, destination='settings', route='settings-category', title=title)

    def update_selection(self):
        from .folder_hub_style import source_tab
        from .appearance import surface
        status = self.owner.settings_status
        section = self.sections[self.selected]
        if status.parent is not section:
            self.detach(status)
            section.add(status)
        for title, button in self.buttons.items():
            selected = bool(self.wide and title == self.selected)
            source_tab(button, selected)
            surface(button, radius=8, background='hover' if selected else 'transparent',
                    foreground='text', outlined=False, eink_outlined=False, eink_selected=selected)

    def reflow(self):
        if self._reflowing:
            return
        self._reflowing = True
        try:
            self._reflow()
        finally:
            self._reflowing = False

    def _reflow(self):
        from .fold_layout import seam_fraction
        app = self.owner
        width = app.adaptive.content_width('settings', margin=0)
        seam = seam_fraction(app, self)
        was_wide = self.wide
        self.wide = width >= 640 or seam is not None
        screens = app.routes.screens['settings']
        active = app.native_host.state.destination == 'settings'
        category_on_top = bool(screens and screens[-1][0] == 'settings-category')
        sidebar_width = (width * seam if seam is not None
                         else min(320, max(240, width * .32)))
        detail_width = width - sidebar_width if self.wide else width
        for section in self.sections.values():
            fit_section(section, detail_width)
        fit_section(self.sidebar.content, sidebar_width if self.wide else width)
        if self.wide:
            self.sidebar.style.flex = 0
            # A partially folded Duo uses the physical seam, including rail/safe areas.
            self.sidebar.style.width = sidebar_width
            if category_on_top and active:
                self.detach(self.options[self.selected])
                app.routes.trim('settings', len(screens) - 1)
                app.routes.render('settings')
            if self.detail.parent is None:
                self.add(self.detail)
            # A nested page can still own the compact category beneath it. Wait
            # for native Back before moving that retained category to the root.
            if not any(screen[0] == 'settings-category' for screen in screens):
                view = self.options[self.selected]
                if view.parent is not self.detail:
                    self.detach(view)
                    for child in list(self.detail.children):
                        self.detail.remove(child)
                    self.detail.add(view)
        else:
            self.sidebar.style.flex = 1
            from toga.style.pack import NONE
            if self.sidebar.style.width != NONE:
                del self.sidebar.style.width
            if self.detail.parent is self:
                self.remove(self.detail)
            if was_wide and active and not screens:
                self.choose(self.selected)
        self.update_selection()
