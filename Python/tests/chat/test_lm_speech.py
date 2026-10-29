"""Answer playback uses silent fixtures, never the user's speakers."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.lm.domain import conversation, message
from features.lm.ui.conversation_view import ConversationView


class SilentSpeech:
    ready = True
    error = 'Test voice unavailable'
    utterance_limit = 32
    sentence_breaks = False
    native_word_events = False

    def __init__(self):
        self.spoken = []
        self.stops = 0
        self.closed = False

    def speak(self, text, voice, speed, token):
        self.spoken.append((text, voice, speed, token))

    def stop(self):
        self.stops += 1

    def close(self):
        self.closed = True


class AnswerSpeechTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.view = ConversationView()
        self.addCleanup(self.view.deleteLater)
        self.addCleanup(self.view.close)
        self.engine = SilentSpeech()
        factory = patch('features.lm.ui.answer_speech.AnswerSpeech.create_adapter', return_value=self.engine)
        self.factory = factory.start()
        self.addCleanup(factory.stop)
        self.data = conversation(model='fixture')
        self.user = message('user', 'User question')
        self.first = message('assistant', '**Hello** world.', reasoning='Reasoning is not part of the answer.')
        self.second = message('assistant', 'Second answer.')
        self.data['messages'] = [self.user, self.first, self.second]
        self.view.resize(700, 500)
        self.view.sync(self.data)
        self.view.show()
        self.app.processEvents()

    def test_speaker_toggles_rendered_answer_at_default_voice_and_speed(self):
        self.factory.assert_not_called()
        self.assertTrue(self.view.bubbles[self.user['id']].speak_button.isHidden())
        bubble = self.view.bubbles[self.first['id']]
        self.assertGreater(bubble.speak_button.x(), bubble.copy_button.geometry().right())
        bubble.speak_button.click()
        self.assertEqual(self.engine.spoken[0][:3], ('Hello world.', '', 1))
        self.assertTrue(bubble.speak_button.isChecked())
        self.assertEqual(bubble.speak_button.accessibleName(), 'Stop reading answer')
        token = self.engine.spoken[-1][3]
        bubble.speak_button.click()
        self.assertFalse(bubble.speak_button.isChecked())
        self.assertEqual(bubble.speak_button.accessibleName(), 'Read answer aloud')
        count = len(self.engine.spoken)
        self.engine.completed(token)
        self.assertEqual(len(self.engine.spoken), count)
        bubble.speak_button.click()
        self.assertEqual(self.engine.spoken[-1][0], 'Hello world.')

    def test_switching_answers_retires_previous_playback_and_completion_resets_button(self):
        first, second = (self.view.bubbles[entry['id']] for entry in (self.first, self.second))
        first.speak_button.click()
        old_token = self.engine.spoken[-1][3]
        second.speak_button.click()
        self.assertFalse(first.speak_button.isChecked())
        self.assertTrue(second.speak_button.isChecked())
        count = len(self.engine.spoken)
        self.engine.completed(old_token)
        self.assertEqual(len(self.engine.spoken), count)
        self.engine.completed(self.engine.spoken[-1][3])
        self.assertFalse(second.speak_button.isChecked())
        self.assertIsNone(self.view.speech.active)

    def test_long_answer_chunks_stop_on_hide_and_conversation_change(self):
        self.first['content'] = 'A longer answer with several words. ' * 20
        self.view.sync(self.data)
        self.view.bubbles[self.first['id']].speak_button.click()
        self.engine.completed(self.engine.spoken[-1][3])
        self.assertEqual(len(self.engine.spoken), 2)
        self.view.hide()
        count = len(self.engine.spoken)
        self.engine.completed(self.engine.spoken[-1][3])
        self.assertEqual(len(self.engine.spoken), count)
        self.assertIsNone(self.view.speech.active)
        self.view.show()
        self.view.bubbles[self.first['id']].speak_button.click()
        self.view.sync(conversation(model='other'))
        self.assertIsNone(self.view.speech.active)
        self.assertEqual(self.view.speech.session.ranges, [])

    def test_missing_voice_reports_error_and_streaming_or_empty_answers_cannot_start(self):
        errors = []
        self.view.speech_error.connect(errors.append)
        self.engine.ready = False
        self.view.bubbles[self.first['id']].speak_button.click()
        self.assertIn('unavailable', errors[-1])
        self.assertFalse(self.view.bubbles[self.first['id']].speak_button.isChecked())
        self.assertEqual(self.engine.spoken, [])
        self.first['status'] = 'streaming'
        self.second['content'] = ''
        self.view.sync(self.data)
        self.assertFalse(self.view.bubbles[self.first['id']].speak_button.isEnabled())
        self.assertFalse(self.view.bubbles[self.second['id']].speak_button.isEnabled())

    def test_destroying_the_view_disposes_playback_without_a_close_event(self):
        view = ConversationView()
        view.sync(self.data)
        view.toggle_speech(self.first['id'])
        session = view.speech.session
        view.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.assertTrue(session.closed)
        self.assertTrue(self.engine.closed)
        self.assertEqual(session.ranges, [])
