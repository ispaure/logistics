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


def speech_voice_setting(app):
    """Load offline voice names on demand, without retaining a speech engine."""
    import asyncio
    from commonUtils.ui.native.speech import NativeSpeech
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
