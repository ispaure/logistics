"""Automatically discover installed read-aloud voices for the retained settings page."""
import asyncio
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.ui.native.forms import FittedLabel as SettingsLabel


def speech_voice_setting(app):
    """Refresh on entry without retaining an idle speech engine or duplicating loads."""
    from commonUtils.ui.native.speech import NativeSpeech
    system = 'System default'
    saved = app.preferences.values['speech_voice']
    choice = toga.Selection(items=[system] + ([saved] if saved else []),
                            value=saved or system, style=Pack(height=48))
    status = SettingsLabel('Loading installed voices…', style=Pack(font_size=12))
    spinner = toga.ActivityIndicator()

    def save(widget, **kwargs):
        try:
            app.preferences.save(speech_voice='' if widget.value == system else widget.value)
            status.text = 'Read-aloud voice saved on this device.'
        except (OSError, ValueError) as error:
            status.text = str(error)

    def populate(voices):
        selected = app.preferences.values['speech_voice']
        choice.on_change = None
        try:
            choice.items = [system, *sorted(voices)]
            picker = getattr(choice._impl, 'native_picker', None)
            if picker is not None:
                picker.reloadAllComponents()
            choice.value = selected if selected in voices else system
        finally:
            choice.on_change = save
        return bool(selected and selected not in voices)

    async def load():
        refresh.enabled = False
        status.text = 'Loading installed voices…'
        spinner.start()
        engine = None
        try:
            engine = NativeSpeech(app.loop)
            for _ in range(150):
                if engine.ready or engine.error:
                    break
                await asyncio.sleep(.1)
            if not engine.ready:
                populate({})
                status.text = engine.error or 'Speech engine did not start. Try refreshing voices.'
                return
            missing = populate(engine.voices)
            status.text = ('Saved voice unavailable; using the system default.' if missing
                           else 'Choose an installed offline voice.')
        except Exception as error:
            populate({})
            status.text = 'Voices unavailable: ' + str(error)[:180]
        finally:
            try:
                if engine is not None:
                    engine.close()
            finally:
                spinner.stop()
                refresh.enabled = True

    task = None
    def start(widget=None, **kwargs):
        nonlocal task
        if task is None or task.done():
            task = app.loop.create_task(load())
            app.speech_voice_load_task = task
        return task

    choice.on_change = save
    refresh = toga.Button('Refresh voices', on_press=start, style=Pack(height=48))
    app.speech_voice_choice = choice
    box = toga.Box(children=[toga.Label('Read-aloud voice'), choice, refresh, spinner, status],
                   style=Pack(direction=COLUMN))
    box._settings_on_open = start
    start()
    return box
