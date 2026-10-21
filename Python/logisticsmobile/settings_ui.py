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
    from .appearance import list_button
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
    from .appearance import apple_color
    return _forms.disclosure(button, apple_color=apple_color)


def group_rows(rows, *, icon_inset=False):
    from .appearance import surface
    return _forms.group_rows(rows, surface=surface, icon_inset=icon_inset,
                             background='settings_group', separator='settings_separator')


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
    # Keep the switch's native accessible label with a separate visible title.
    switch.text = ''
    switch.style.flex = 0
    switch.style.width = 64
    from .appearance import accessible_name
    accessible_name(switch, title)
    row = toga.Box(children=[
        SettingsLabel(title, style=Pack(flex=1)),
        switch,
    ], style=Pack(direction=ROW, align_items=CENTER, margin_bottom=8))
    row._settings_switch_row = True
    row._settings_note = connection_note(explanation)
    row._settings_note.style.font_size = 13
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
        super().__init__(style=Pack(direction=ROW, flex=1))
        self.owner = app
        from .appearance import surface, list_button
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
        self.options = SettingsPages({title: lambda title=title: toga.ScrollContainer(horizontal=False,
            content=self.sections[title], style=Pack(flex=1)) for title in sections})
        self.buttons = {}
        from .control_icons import button_icons
        surface(self, radius=0, background='settings_background', outlined=False, eink_outlined=False)
        menu = toga.Box(style=Pack(direction=COLUMN, margin=16))
        menu.add(surface(toga.Label('Settings', style=Pack(font_size=28, font_weight='bold', margin_bottom=24)),
                         radius=0, background='transparent', foreground='text', outlined=False, eink_outlined=False))
        icons = {'App': 'preferences', 'Appearance': 'appearance', 'Read aloud': 'speaker',
                 'Markdown': 'edit', 'Text': 'edit', 'EPUB': 'books', 'Books & Comics': 'books', 'LM Chat': 'chat',
                 'Workspaces': 'folder', 'Reset': 'preferences', 'Help': 'help', 'About': 'info'}
        rows = []
        for title in sections:
            def choose(widget=None, selected=title, **kwargs):
                self.choose(selected)
            button = list_button(toga.Button(title, on_press=choose, style=Pack(height=52)))
            button._settings_list_styled = True
            button_icons(button, [(icons[title], '')])
            disclosure(button)
            button._settings_row = True
            # Match the initial unselected state during detached construction,
            # rather than restyling every native button on the first reflow.
            button._settings_selected = False
            surface(button, radius=8, background='transparent', foreground='text',
                    outlined=False, eink_outlined=False)
            self.buttons[title] = button
            rows.append(button)
            end_group = title == ('Appearance' if 'Appearance' in sections else 'App')
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
        self.add(self.sidebar)

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
        self.detach(view)
        if self.wide:
            for child in list(self.detail.children):
                self.detail.remove(child)
            self.detail.add(view)
        else:
            # The guard above also protects wide layouts; do not checkpoint twice.
            self.owner.show_view(view, checkpoint=False, destination='settings', route='settings-category', title=title)

    def update_selection(self, *, show_detail=False):
        from .appearance import surface
        status = self.owner.settings_status
        if show_detail:
            section = self.sections[self.selected]
            if status.parent is not section:
                self.detach(status)
                section.add(status)
        for title, button in self.buttons.items():
            selected = bool(self.wide and self.detail_requested and title == self.selected)
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
        from .fold_layout import seam_fraction
        app = self.owner
        width = app.adaptive.content_width('settings', margin=0)
        seam = seam_fraction(app, self)
        was_wide = self.wide
        self.wide = width >= 640 or seam is not None
        screens = app.routes.screens['settings']
        active = app.native_host.state.destination == 'settings'
        category_on_top = bool(screens and screens[-1][0] == 'settings-category')
        if active and not was_wide and not screens and getattr(self, '_category_on_stack', False):
            self.detail_requested = False
        sidebar_width = (width * seam if seam is not None
                         else min(320, max(240, width * .32)))
        detail_width = width - sidebar_width if self.wide else width
        self.detail_width = detail_width
        menu_width = sidebar_width if self.wide else width
        # The category menu is static. Avoid native text reads, sizing and
        # drawable updates for every row on each tab/resize callback.
        if getattr(self, '_menu_fit_width', None) != menu_width:
            fit_section(self._menu, menu_width)
            self._menu_fit_width = menu_width
        if self.sidebar.content is None:
            self.sidebar.content = self._menu
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
            if self.detail_requested and not any(screen[0] == 'settings-category' for screen in screens):
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
            if active and not screens and self.detail_requested:
                self.choose(self.selected)
        self._category_on_stack = any(screen[0] == 'settings-category' for screen in screens)
        self.update_selection(show_detail=(self.wide and self.detail_requested) or category_on_top)
        if (self.wide and self.detail_requested) or category_on_top:
            self.fit_detail(self.selected)


def settings_sections(app):
    """Create preference controls only when their category is first opened."""
    from .hub_ui import heading
    app.settings_status = SettingsLabel(app.preferences.error, style=Pack(margin_top=12))
    def category(title):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(heading(title))
        return box

    def application():
        box = category('App')
        app.restore_choice = toga.Switch('Restore last document',
            value=app.preferences.values['restore_last_document'] == 'true', style=Pack(height=48))
        app.clear_documents_choice = toga.Switch('Clear on restart',
            value=app.preferences.values['clear_unmodified_documents_on_restart'] == 'true',
            style=Pack(height=48))
        box.add(switch_row(app, 'Restore last document', app.restore_choice,
            'Resume the last active document when the app starts, including ordinary EPUB and comic readers. '
            'Session-only documents, including those loaded using session-only credentials, are never restored.'))
        box.add(switch_row(app, 'Close saved documents on restart', app.clear_documents_choice,
            'Closes documents with no pending changes in Open documents when the app restarts. '
            'The last active document is kept when Restore last document is on. '
            'Stored documents, reading progress and unsaved drafts are kept.'))
        box.add(toga.Label('Preferences save automatically on this device.', style=Pack(font_size=12)))
        box.add(toga.Button('Reload preferences', on_press=app.reload_preferences, style=Pack(height=48)))
        if app.scene_manager.supported:
            box.add(toga.Button('New window', on_press=app.scene_manager.new_window, style=Pack(height=48)))
            if app.window_id != 'primary':
                box.add(toga.Button('Close window', on_press=lambda widget, **kw:
                    app.scene_manager.close_window(app), style=Pack(height=48)))
        app.restore_choice.on_change = app.save_preferences
        app.clear_documents_choice.on_change = app.save_preferences
        return box

    def appearance():
        box = category('Appearance')
        app.snow_choice = toga.Switch('Seasonal snow',
            value=app.preferences.values['seasonal_snow'] == 'true', style=Pack(height=48))
        box.add(switch_row(app, 'Seasonal snow', app.snow_choice,
            'Snow from December 15 through January 2, inclusive. On by default. '
            'Disabled in high-contrast / E Ink mode. Saved immediately.'))
        app.snow_choice.on_change = app.change_seasonal_snow
        if not type(app._impl).__module__.startswith('toga_android.'):
            return box
        app.android_eink_choice = toga.Switch('High contrast / E Ink',
            value=app.preferences.values['android_eink'] == 'true', style=Pack(height=48))
        box.add(switch_row(app, 'High contrast / E Ink', app.android_eink_choice,
            'Use black text on white, strong borders and simpler controls. Overrides dark mode and reader colors '
            'without changing images or files. Saved immediately. No BOOX hardware refresh control.'))
        app.android_eink_choice.on_change = app.change_android_eink
        return box

    def speech():
        box = category('Read aloud')
        box.add(speech_voice_setting(app))
        app.session_speech_choice = toga.Switch('Session-only speech while locked',
            value=app.preferences.values['session_speech_when_locked'] == 'true',
            on_change=app.change_session_speech, style=Pack(height=48))
        box.add(switch_row(app, 'Session-only speech while locked', app.session_speech_choice,
            'Allow already-started read-aloud from session-only credentials to keep playing '
            'and show system playback controls while locked. Off by default. This choice is saved. '
            'It does not unlock credentials or permit new file reads while locked.'))
        return box

    def text_size(title, key):
        box = category(title)
        box.add(toga.Label(title + ' font size'))
        choice = toga.Selection(items=[str(size) for size in range(12, 33)],
            value=app.preferences.values[key], style=Pack(height=48))
        setattr(app, key + '_choice', choice)
        choice.on_change = app.save_preferences
        box.add(choice)
        box.add(toga.Label('Pinch to adjust. Saved for this format on this device.', style=Pack(font_size=12)))
        if title in {'Markdown', 'EPUB'}:
            justify_key = title.lower() + '_justify'
            justify = toga.Switch('Justify text', value=app.preferences.values[justify_key] == 'true', style=Pack(height=48))
            setattr(app, justify_key + '_choice', justify)
            box.add(switch_row(app, 'Justify text', justify,
                'Align paragraphs and lists to both edges. Saved for this format on this device.'))
            justify.on_change = app.save_preferences
        return box

    def books():
        box = category('Books & Comics')
        from .magnifier import setting
        box.add(toga.Label('Comic & PDF magnifier zoom'))
        app.magnifier_choice = setting(app)
        box.add(app.magnifier_choice)
        box.add(toga.Label('Keep holding; tap −/+ just outside the lens’s upper corners.\nShared across comics and PDFs. Saved immediately.', style=Pack(font_size=12)))
        box.add(toga.Button('Saved books & comics…', on_press=app.show_saved_files, style=Pack(height=48)))
        box.add(toga.Label('Use Appearance in an open reader\nto adjust its pages.', style=Pack(font_size=12)))
        return box

    def chat():
        box = category('LM Chat')
        box.add(toga.Button('Server & generation settings…', on_press=app.show_chat_configuration, style=Pack(height=48)))
        return box

    def workspaces():
        box = category('Workspaces')
        if type(app._impl).__module__.startswith('toga_android.'):
            box.add(toga.Button('Local / LocalCrypt location…', on_press=app.show_collection_storage, style=Pack(height=48)))
        app.show_legacy_choice = toga.Switch('Show Legacy',
            value=getattr(app, 'show_legacy_session', False),
            on_change=app.change_show_legacy, style=Pack(height=48))
        box.add(switch_row(app, 'Show Legacy', app.show_legacy_choice,
            'Show Legacy- folders in Workspaces, file browsers and library shortcuts, '
            'and credential choices whose names start with Legacy. This choice lasts only until the app closes.'))
        box.add(toga.Button('rclone connections…', on_press=app.show_cloud_connections, style=Pack(height=48)))
        box.add(toga.Button('SMB shares…', on_press=app.show_smb_connection, style=Pack(height=48)))
        return box

    def reset():
        box = category('Reset')
        box.add(toga.Button('Erase all app data…', on_press=app.show_app_reset, style=Pack(height=48)))
        box.add(SettingsLabel('Delete private files, local app data, settings and metadata. Review the full scope before confirming.'))
        return box

    def help():
        box = category('Help')
        if type(app._impl).__module__.startswith('toga_android.'):
            box.add(toga.Button('Developer settings…', on_press=app.open_android_developer_settings, style=Pack(height=48)))
        from .documentation_ui import show_documentation
        box.add(toga.Button('Mobile documentation', on_press=lambda widget, **kw: show_documentation(app),
                            style=Pack(height=48)))
        return box

    def about():
        box = category('About')
        app.build_version_label = toga.Label(build_information(app.version),
            style=Pack(font_size=12, color='#808080'))
        box.add(app.build_version_label)
        return box

    sections = {'App': application, 'Appearance': appearance}
    sections['Read aloud'] = speech
    sections['Markdown'] = lambda: text_size('Markdown', 'markdown_font_size')
    sections['Text'] = lambda: text_size('Text', 'text_font_size')
    sections['EPUB'] = lambda: text_size('EPUB', 'epub_font_size')
    sections['Books & Comics'] = books
    sections['LM Chat'] = chat
    sections['Workspaces'] = workspaces
    sections['Reset'] = reset
    sections['Help'] = help
    sections['About'] = about
    return sections
