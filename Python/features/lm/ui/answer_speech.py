"""One default-voice read-aloud session for a desktop conversation."""
from commonUtils.ui import pyside as qt
from commonUtils.runtime.speech import SpeechSession
from commonUtils.ui.readers.qt_speech import QtScheduler, QtSpeechEngine


class AnswerSpeech(qt.QObject):
    changed = qt.Signal(object)
    error = qt.Signal(str)

    def __init__(self, owner, *, adapter_factory=None):
        super().__init__(owner)
        self.adapter_factory = adapter_factory
        self.session = None
        self.active = self.target = None
        self.scheduler = QtScheduler(self)
        owner.installEventFilter(self)
        owner.window().installEventFilter(self)
        owner.destroyed.connect(self.dispose)

    def create_adapter(self):
        if self.adapter_factory is not None:
            return self.adapter_factory(self)
        from PySide6.QtTextToSpeech import QTextToSpeech
        if not QTextToSpeech.availableEngines():
            raise RuntimeError('No system speech engine is installed.')
        engine = QTextToSpeech(self)
        # Leave the engine's default voice/locale in place; use normal speed.
        return QtSpeechEngine(engine, QTextToSpeech, self.scheduler)

    def toggle(self, key, text):
        if self.active == key:
            self.stop()
            return
        self.stop()
        if not text.strip():
            return
        try:
            if self.session is None:
                self.session = SpeechSession(self.create_adapter(), on_range=lambda *args: None,
                                             on_state=self.state_changed)
            self.target = key
            self.session.play(text)
        except (ImportError, RuntimeError, ValueError) as error:
            self.stop()
            self.error.emit(f'Read aloud is unavailable: {error}')

    def state_changed(self, state, message):
        self.active = self.target if state == 'speaking' else None
        self.changed.emit(self.active)
        if state == 'unavailable':
            self.error.emit(f'Read aloud is unavailable: {message}')

    def stop(self):
        self.target = None
        if self.session is not None:
            self.session.stop()
        else:
            self.active = None
            self.changed.emit(None)

    def dispose(self):
        self.target = None
        if self.session is not None:
            self.session.dispose()

    def eventFilter(self, watched, event):
        if event.type() in (qt.QEvent.Type.Hide, qt.QEvent.Type.Close):
            self.stop()
        return False
