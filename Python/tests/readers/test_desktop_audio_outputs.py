"""Desktop route notifications and protected speech through real Qt owners."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from types import SimpleNamespace
from unittest.mock import Mock, patch

from commonUtils.runtime.speech import SpeechSession
from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.readers.read_aloud import ReadAloud
from desktop.speech_outputs import monitor_private_speech
from features.lm.ui.answer_speech import AnswerSpeech
from features.video.ui.lifecycle import DesktopLifecycle
from services.documents.ui.private_views import protect_private_view

TEST_STAGE = TestStage.REGRESSION


class Devices(qt.QObject):
    audioOutputsChanged = qt.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.route = b'Jade'
        self.visible = [self.route]

    def defaultAudioOutput(self):
        return SimpleNamespace(id=lambda: self.route)

    def audioOutputs(self):
        return [SimpleNamespace(id=lambda value=value: value) for value in self.visible]

    def select(self, route):
        self.route = route
        self.visible = [route]
        self.audioOutputsChanged.emit()


class DesktopAudioOutputTests(QtTestCase):
    def setUp(self):
        super().setUp()
        self.window = qt.QMainWindow()
        self.addCleanup(self.window.deleteLater)
        with patch('services.documents.ui.audio_outputs.QMediaDevices', Devices):
            self.monitor = monitor_private_speech(self.window)
        self.devices = self.monitor.devices

    def start(self, owner, kind=ReadAloud):
        control = kind(owner, lambda: '') if kind is ReadAloud else kind(owner)
        engine = Mock(spec=['ready', 'speak', 'stop', 'close'], ready=True)
        control.session = SpeechSession(engine, on_state=lambda *_: None, on_range=lambda *_: None)
        control.session.play('Copper satellites whisper violet marmalade. A blue satellite returns.')
        return control.session, engine

    def test_current_protected_provider_stops_and_late_completion_cannot_speak(self):
        public, public_engine = self.start(self.window)
        document = qt.QWidget(self.window)
        document.resource_provider = Mock(return_value=SimpleNamespace(session_only=False))
        protect_private_view(document, document.resource_provider())
        private, engine = self.start(document)
        token = private.token
        document.resource_provider.return_value = SimpleNamespace(session_only=True)
        self.devices.visible.append(b'Ochre')
        self.devices.audioOutputsChanged.emit()
        self.assertEqual(private.state, 'speaking')
        self.devices.select(b'Ochre')
        self.assertEqual(private.state, 'stopped')
        private.completed(token)
        engine.speak.assert_called_once()
        public.completed(public.token)
        self.assertEqual(public.state, 'speaking')
        self.assertEqual(public_engine.speak.call_count, 2)

    def test_process_scope_stops_paused_document_and_speaking_answer_on_loss(self):
        reader, reader_engine = self.start(self.window)
        reader.pause()
        answer, answer_engine = self.start(self.window, AnswerSpeech)
        token = answer.token
        self.devices.visible.clear()  # Qt can briefly retain the old default ID.
        with patch('desktop.speech_outputs.session_contexts', return_value=('fixture.session',)):
            self.devices.audioOutputsChanged.emit()
        self.assertEqual((reader.state, answer.state), ('stopped', 'stopped'))
        reader.resume()
        answer.completed(token)
        reader_engine.speak.assert_called_once()
        answer_engine.speak.assert_called_once()

    def test_first_identifiable_output_locks_only_protected_video(self):
        window = SimpleNamespace(resume_guard=None)
        life = SimpleNamespace(window=lambda: window, pause=Mock())
        self.monitor.selected = b''
        self.monitor.changed.connect(lambda previous: DesktopLifecycle.outputs_changed(life, previous))
        self.devices.select(b'Ochre')
        life.pause.assert_not_called()
        self.monitor.selected = b''
        window.resume_guard = Mock()
        self.devices.select(b'Jade')
        life.pause.assert_called_once_with()
