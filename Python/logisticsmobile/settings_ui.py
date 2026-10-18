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
