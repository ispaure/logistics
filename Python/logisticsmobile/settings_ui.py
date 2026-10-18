"""Compact preference rows and offline installed-build information."""
import json
from pathlib import Path
import sys
from textwrap import fill

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from services.build_version import BuildVersion, installed_build


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
    return toga.Box(children=[
        toga.Label(fill(title, width=26), style=Pack(flex=1)),
        info,
        switch,
    ], style=Pack(direction=ROW, align_items=CENTER, margin_bottom=8))


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
    status = toga.Label('Uses an installed offline system voice.', style=Pack(font_size=12))

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
        self.selected = next(iter(sections))
        self.wide = None
        self._reflowing = False
        self.options = {title: toga.ScrollContainer(horizontal=False, content=section,
                       style=Pack(flex=1)) for title, section in sections.items()}
        self.buttons = {}
        menu = toga.Box(style=Pack(direction=COLUMN, margin=16))
        menu.add(toga.Label('Settings', style=Pack(font_size=22, font_weight='bold', margin_bottom=16)))
        from commonUtils.ui.native.presentation import list_button
        for title in sections:
            def choose(widget=None, selected=title, **kwargs):
                self.choose(selected)
            button = list_button(toga.Button(title, on_press=choose, style=Pack(height=52, margin_bottom=4)))
            self.buttons[title] = button
            menu.add(button)
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
        status = self.owner.settings_status
        section = self.sections[self.selected]
        if status.parent is not section:
            self.detach(status)
            section.add(status)
        for title, button in self.buttons.items():
            button.text = title if self.wide else title + '  ›'
            source_tab(button, bool(self.wide and title == self.selected))

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
        if self.wide:
            self.sidebar.style.flex = 0
            # A partially folded Duo uses the physical seam, including rail/safe areas.
            self.sidebar.style.width = ((self.layout.content_width or width) * seam if seam is not None
                                        else min(320, max(240, width * .32)))
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
