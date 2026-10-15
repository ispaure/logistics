"""Platform speech adapters. Only installed, offline voices are offered."""
import weakref

_delegate_class = None


class NativeSpeech:
    def __init__(self, loop):
        self.loop, self.ready, self.error, self.closed = loop, False, '', False
        self.voices, self.completed = {}, lambda *args: None
        self.failed = lambda *args: None
        self.default_voice = ''
        from toga.platform import get_factory
        backend = get_factory().WebView.__module__
        self.backend = backend
        try:
            if backend.startswith('toga_android.'):
                self.android()
            elif backend.startswith('toga_iOS.'):
                self.apple()
            else:
                self.error = 'Read-aloud requires an Android or iOS speech engine.'
        except Exception:
            self.error = 'Speech engine unavailable. Install an offline system voice.'

    def deliver(self, token):
        if not self.closed:
            self.loop.call_soon_threadsafe(lambda: None if self.closed else self.completed(token))

    def failure(self, token):
        if not self.closed:
            self.loop.call_soon_threadsafe(lambda: None if self.closed else self.failed(token))

    def android(self):
        from android.speech.tts import TextToSpeech
        from org.beeware.android import MainActivity
        from java import dynamic_proxy
        owner = weakref.ref(self)
        class Init(dynamic_proxy(TextToSpeech.OnInitListener)):
            def onInit(self, status):
                engine = owner()
                if engine is not None:
                    engine.loop.call_soon_threadsafe(engine.initialized, status)
        from io.github.ispaure.logistics.books import BookSpeechListener
        class Complete(dynamic_proxy(BookSpeechListener.Listener)):
            def completed(self, token):
                engine = owner()
                if engine is not None:
                    engine.deliver(str(token))
            def failed(self, token):
                engine = owner()
                if engine is not None:
                    engine.failure(str(token))
        self.listener, self.init_listener = Complete(), Init()
        self.progress_listener = BookSpeechListener(self.listener)
        self.native = TextToSpeech(MainActivity.singletonThis, self.init_listener)

    def initialized(self, status):
        try:
            self.load_android_voices(status)
        except Exception:
            self.ready = False
            self.error = 'Offline voices could not be loaded. Check system speech settings.'

    def load_android_voices(self, status):
        if self.closed:
            return
        if status != 0:
            self.error = 'Speech engine unavailable. Install an offline system voice.'
            return
        self.native.setOnUtteranceProgressListener(self.progress_listener)
        voices = self.native.getVoices()
        if voices is not None:
            for voice in voices.toArray():
                if not voice.isNetworkConnectionRequired() and 'notInstalled' not in {str(v) for v in voice.getFeatures().toArray()}:
                    label = str(voice.getLocale().toLanguageTag()) + ' · ' + str(voice.getName())
                    self.voices[label] = voice
        self.default_voice = next((label for label in self.voices if label.startswith('en-US')), next(iter(self.voices), ''))
        self.ready = bool(self.voices)
        if not self.ready:
            self.error = 'No installed offline voice. Install one in Android text-to-speech settings.'

    def apple(self):
        global _delegate_class
        import ctypes
        ctypes.CDLL('/System/Library/Frameworks/AVFoundation.framework/AVFoundation')
        from rubicon.objc import ObjCClass, ObjCProtocol, objc_method, objc_property
        if _delegate_class is None:
            class LogisticsBookSpeechDelegate(ObjCClass('NSObject'), protocols=(ObjCProtocol('AVSpeechSynthesizerDelegate'),)):
                owner = objc_property(object, weak=True)

                @objc_method
                def speechSynthesizer_didFinishSpeechUtterance_(self, synth, utterance) -> None:
                    engine = self.owner
                    if engine is not None and getattr(engine, 'utterance', None) is not None:
                        if utterance.ptr.value == engine.utterance.ptr.value:
                            engine.deliver(engine.token)
                @objc_method
                def speechSynthesizer_didCancelSpeechUtterance_(self, synth, utterance) -> None:
                    engine = self.owner
                    if engine is not None and getattr(engine, 'utterance', None) is not None:
                        if utterance.ptr.value == engine.utterance.ptr.value:
                            engine.failure(engine.token)
            _delegate_class = LogisticsBookSpeechDelegate
        self.native = ObjCClass('AVSpeechSynthesizer').alloc().init()
        self.delegate = _delegate_class.alloc().init()
        self.delegate.owner = self
        self.native.delegate = self.delegate
        self.utterance = None
        voices = ObjCClass('AVSpeechSynthesisVoice').speechVoices
        for voice in (voices() if callable(voices) else voices):
            self.voices[str(voice.language) + ' · ' + str(voice.name)] = voice
        default = ObjCClass('AVSpeechSynthesisVoice').voiceWithLanguage('en-US')
        self.default_voice = next((label for label, voice in self.voices.items() if default is not None and str(voice.identifier) == str(default.identifier)), next(iter(self.voices), ''))
        self.ready = bool(self.voices)
        if not self.ready:
            self.error = 'No installed voice. Add a system voice in Spoken Content settings.'

    def speak(self, text, voice, speed, token):
        if self.closed or not self.ready or voice not in self.voices:
            raise RuntimeError('An installed offline voice is required.')
        self.token = token
        if self.backend.startswith('toga_android.'):
            if self.native.setVoice(self.voices[voice]) != 0 or self.native.setSpeechRate(speed) != 0:
                raise RuntimeError('Voice unavailable.')
            if self.native.speak(text, 0, None, token) != 0:
                raise RuntimeError('Speech engine failed.')
        else:
            from rubicon.objc import ObjCClass
            utterance = ObjCClass('AVSpeechUtterance').speechUtteranceWithString(text)
            utterance.voice = self.voices[voice]
            utterance.rate = min(1.0, max(.1, .5 * speed))
            self.utterance = utterance
            self.native.speakUtterance(utterance)

    def stop(self):
        if getattr(self, 'native', None) is not None:
            if self.backend.startswith('toga_android.'):
                self.native.stop()
            else:
                self.utterance = None
                self.native.stopSpeakingAtBoundary(0)

    def close(self):
        if not self.closed:
            self.closed = True
            self.stop()
            if getattr(self, 'native', None) is not None:
                if self.backend.startswith('toga_android.'):
                    self.progress_listener.detach()
                    self.native.shutdown()
                else:
                    self.native.delegate = None
            self.voices = {}
