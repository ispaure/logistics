"""Selected-output queries and native lifetime only; consent lives in AudioOutput."""
from services.audio_output import output


def value(owner, name):
    result = getattr(owner, name)
    return result() if callable(result) else result


def monitor(app, changed, interrupted):
    backend = type(app._impl).__module__
    if backend.startswith('toga_iOS.'):
        return AppleOutputs(changed, interrupted)
    if backend.startswith('toga_android.'):
        return AndroidOutputs(app, changed, interrupted)
    if backend.startswith('toga_dummy.'):
        return DummyOutputs()
    raise RuntimeError('Audio output identification is unavailable on this platform.')


class DummyOutputs:
    """Toga's no-audio test backend; never used on an actual mobile platform."""
    def outputs(self):
        return (output('dummy', 'silent', 'Test output'),)

    def in_call(self):
        return False

    def dispose(self):
        pass


class AppleOutputs:
    def __init__(self, changed, interrupted):
        import ctypes
        from rubicon.objc import ObjCClass, Block, objc_id
        self.library = ctypes.CDLL('/System/Library/Frameworks/AVFAudio.framework/AVFAudio')
        self.audio = value(ObjCClass('AVAudioSession'), 'sharedInstance')
        self.center = value(ObjCClass('NSNotificationCenter'), 'defaultCenter')
        self.tokens = []
        self.blocks = []
        self.active_interruption = False
        def interruption(note):
            kind = note.userInfo.objectForKey('AVAudioSessionInterruptionTypeKey')
            number = kind if isinstance(kind, int) else (value(kind, 'unsignedIntegerValue') if kind is not None else 1)
            self.active_interruption = number == 1
            interrupted(self.active_interruption)
        for name, callback in [('AVAudioSessionRouteChangeNotification', lambda note: changed()),
                               ('AVAudioSessionInterruptionNotification', interruption)]:
            block = Block(callback, None, objc_id)
            self.blocks.append(block)
            self.tokens.append(self.center.addObserverForName(name, object=None, queue=value(ObjCClass('NSOperationQueue'), 'mainQueue'), usingBlock=block))

    def prepare(self):
        # Activate without submitting audio, then re-query the actual selected route.
        return bool(self.audio.setCategory('AVAudioSessionCategoryPlayback', error=None)
                    and self.audio.setActive(True, error=None))

    def outputs(self):
        ports = value(value(self.audio, 'currentRoute'), 'outputs')
        result = []
        for port in ports:
            kind = str(value(port, 'portType'))
            result.append(output('ios:' + kind, str(value(port, 'UID')), str(value(port, 'portName')),
                                 bluetooth=kind in {'BluetoothA2DPOutput', 'BluetoothHFP', 'BluetoothLE'}))
        return tuple(result) or None

    def in_call(self):
        return self.active_interruption

    def dispose(self):
        for token in self.tokens:
            self.center.removeObserver(token)
        self.tokens.clear()
        self.blocks.clear()


class AndroidOutputs:
    def __init__(self, app, changed, interrupted):
        from java import jclass, dynamic_proxy
        kind = jclass('io.github.ispaure.logistics.audio.AudioOutputs')
        class Listener(dynamic_proxy(kind.Listener)):
            def changed(self):
                changed()
        self.listener = Listener()
        self.native = kind(app._impl.native, self.listener)

    def outputs(self):
        import json
        rows = json.loads(str(self.native.outputs()))
        if rows is None:
            return None
        return tuple(output('android:' + str(row['type']), row['id'], row['name'], bluetooth=row['bluetooth'])
                     for row in rows)

    def in_call(self):
        return bool(self.native.inCall())

    def dispose(self):
        self.native.close()
