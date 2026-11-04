"""Run feedback items 9–11 in one disposable native application."""
import json
from pathlib import Path
import traceback

from commonUtils.testing.stages import TestStage
from .chat_settings_probe import ChatSettingsProbe
from .notes_search_probe import NotesSearchProbe

TEST_STAGE = TestStage.REGRESSION


class ChatNotesFeedbackProbe(NotesSearchProbe):
    async def probe(self, app):
        output = Path(self.paths.cache)
        report = dict(success=False, checks={})
        try:
            for name, check, filename in (
                ('chat_settings', ChatSettingsProbe.probe, 'chat-settings-result.json'),
                ('notes_search', NotesSearchProbe.probe, 'notes-search-result.json'),
            ):
                await check(self, app)
                result = json.loads((output / filename).read_text())
                report['checks'][name] = result
                assert result['success'], result.get('error', name + ' failed')
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'chat-notes-feedback-result.json').write_text(json.dumps(report, indent=2))


def main():
    return ChatNotesFeedbackProbe('Mobile Feedback QA', 'io.github.ispaure.logisticsstorageqa')
