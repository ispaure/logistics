"""Discoverable device-local Bluetooth consent management for all app audio."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .forms import SettingsLabel
from ..audio_output import for_app


def controls(app, box):
    owner = for_app(app)
    box.add(SettingsLabel('Bluetooth approval applies to video and all read-aloud only while session-only protection is active. '
        'During protection, changing audio outputs pauses playback. Adding a device never starts playback. '
        'These approvals are saved only on this device.'))
    current = SettingsLabel('')
    status = SettingsLabel('')
    rows = toga.Box(style=Pack(direction=COLUMN))
    def render(widget=None, **kwargs):
        owner.refresh()
        outputs = owner.policy.route
        current.text = 'Current output: ' + (', '.join(item.label for item in outputs) if outputs else 'Unavailable')
        rows.clear()
        for identity, name in owner.approved().items():
            def remove(widget=None, identity=identity, **kwargs):
                values = owner.approved()
                values.pop(identity, None)
                try:
                    owner.save(values)
                    status.text = 'Approval removed. Protected playback stays paused; ordinary playback is unaffected.'
                    render()
                except (OSError, ValueError) as error:
                    status.text = str(error)
            rows.add(toga.Box(children=[SettingsLabel(name + ' · ' + identity[:8], style=Pack(flex=1)),
                toga.Button('Remove', on_press=remove, style=Pack(height=48))], style=Pack(direction=ROW)))
        if not rows.children:
            rows.add(SettingsLabel('No approved Bluetooth devices. Select a Bluetooth output in system '
                'controls during session-only protection, then press Play or Approve current output.'))
    async def approve(widget=None, **kwargs):
        if not owner.protected():
            status.text = 'Session-only protection is inactive. Ordinary playback does not need Bluetooth approval.'
            return
        owner.pause()
        if owner.prepare():
            owner.refresh()
        owner.offer(explicit=True)
        task = owner.prompt
        if task is not None:
            await task
        status.text = 'Playback remains paused. Press Play in the player when ready.'
        render()
    box.add(current)
    box.add(toga.Button('Refresh output and approvals', on_press=render, style=Pack(height=48)))
    box.add(toga.Button('Approve current output…', on_press=approve, style=Pack(height=48)))
    box.add(rows)
    box.add(status)
    render()
    return rows
