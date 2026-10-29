"""Interactive all-audio Settings checks on explicitly authorized QA devices.

This uses the real selected output and native speech. No route injection, calls,
Bluetooth pairing or personal device changes are automated by this entry point.
"""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import time
from types import SimpleNamespace

import toga
from toga.style import Pack
from features.books.mobile.speech_view import ReadAloudPanel
from mobile.app import LogisticsMobile


async def phase(app, label='ordinary'):
    owner = app.audio_output
    app.show_settings(rebuild=True)
    app.settings_navigation.choose('Audio playback')
    section = app.settings_navigation.sections['Audio playback']
    section.add(toga.Label('QA: ' + label, style=Pack(font_size=20)))
    section.add(toga.Label('Ordinary playback: connect/switch Bluetooth without an approval prompt or list dependency. '
        'With session-only or retained protection: add/decline approval, remove it while speaking, '
        'and switch approved/unapproved outputs; each change stays paused until a separate Play. '
        'In both modes, calls and actual headphone/output loss must still pause without auto-resume.'))
    async def source():
        return SimpleNamespace(text=('This is a synthetic audio privacy test. ' * 100),
                               language='en', breaks=()), 0, None
    panel = ReadAloudPanel(loop=app.loop, app=app, source=source, on_range=lambda *args: None,
                          close=lambda: None, document_title=lambda: 'Synthetic playback QA')
    section.add(panel)
    done = app.loop.create_future()
    def finish(widget=None, **kwargs):
        if not done.done():
            done.set_result(None)
    button = toga.Button('Continue QA', on_press=finish, style=Pack(height=48))
    section.add(button)
    report = dict(scope='User-operated native speech and selected output; no acoustic proof', phase=label,
                  backend=type(app._impl).__module__, events=[])
    target = Path(app.paths.cache) / ('audio-hardware-' + label.replace(' ', '-') + '.json')
    previous = None
    try:
        while not done.done():
            owner.refresh()
            state = dict(output=[dict(id=item.identity[:8], bluetooth=item.bluetooth) for item in owner.policy.route or ()],
                         identified=owner.policy.identified(), protected=owner.protected(), approved_count=len(owner.approved()),
                         explicit_play=owner.policy.manual_play, speech_state=panel.session.state,
                         private=app.screen_privacy.sensitive(), captured=app.screen_privacy.captured)
            if state != previous:
                previous = state
                report['events'].append(dict(at=time.time(), **state))
                temp = target.with_suffix('.tmp')
                temp.write_text(json.dumps(report, indent=2))
                temp.replace(target)
            await asyncio.sleep(.02)
    finally:
        panel.dispose()
        section.remove(panel)
        section.remove(button)
    return report


async def exercise(app):
    if getattr(app, 'startup_task', None) is not None:
        await asyncio.shield(app.startup_task)
    await phase(app)


class AudioHardwareProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'audio-output-qa-private'
        super().startup()

    def on_running(self):
        if getattr(self, '_audio_qa', None) is None:
            self._audio_qa = self.loop.create_task(exercise(self))


def main():
    return AudioHardwareProbe('Audio Playback QA', 'io.github.ispaure.logisticsaudioqa')
