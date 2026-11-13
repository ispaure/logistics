"""Native route monitoring and approval presentation; consent lives in AudioOutput."""
import asyncio
import logging

from services.audio_output import output


def value(owner, name):
    result = getattr(owner, name)
    return result() if callable(result) else result


async def show_approval(app, dialog, *, valid):
    if not type(getattr(app, '_impl', None)).__module__.startswith('toga_iOS.'):
        return await app.main_window.dialog(dialog)

    # Toga 0.5.7 presents alerts from the root controller. Full-screen video
    # and the reader's native panels can already be presented above it.
    from rubicon.objc import ObjCClass
    impl = dialog._impl
    alert = impl.native
    root = app.main_window._impl.native.rootViewController
    for _ in range(20):
        if not valid():
            return None
        presenter = root
        while presenter.presentedViewController:
            presenter = presenter.presentedViewController
        if not value(presenter, 'isBeingPresented') and not value(presenter, 'isBeingDismissed'):
            break
        await asyncio.sleep(.05)
    else:
        return None
    if (value(value(presenter, 'view'), 'window') is None
            or presenter.isKindOfClass(ObjCClass('UIAlertController'))):
        return None

    response = impl.future = app.loop.create_future()
    try:
        presenter.presentViewController(alert, animated=False, completion=None)
        while not response.done():
            await asyncio.wait({response}, timeout=.1)
            # Locking or closing video may dismiss the entire presented stack.
            if not response.done() and (not valid() or alert.presentingViewController is None):
                return None
        return response.result()
    finally:
        presenter = alert.presentingViewController
        if not response.done() and presenter is not None and presenter.presentedViewController == alert:
            presenter.dismissViewControllerAnimated(False, completion=None)


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
        from rubicon.objc import ObjCClass, ObjCInstance, Block, objc_id, objc_const
        self.library = ctypes.CDLL('/System/Library/Frameworks/AVFAudio.framework/AVFAudio')
        self.audio = value(ObjCClass('AVAudioSession'), 'sharedInstance')
        self.center = value(ObjCClass('NSNotificationCenter'), 'defaultCenter')
        self.tokens = []
        self.closed = False
        self.active_interruption = False
        interruption_key = objc_const(self.library, 'AVAudioSessionInterruptionTypeKey')
        route_key = objc_const(self.library, 'AVAudioSessionRouteChangeReasonKey')

        def notification_number(pointer, key, default):
            # Rubicon Block supplies a raw objc_id. Resolve the dictionary key
            # using AVFAudio's exported NSString, as its value is platform-owned.
            info = ObjCInstance(pointer).userInfo
            number = info.get(key) if info is not None else None
            if number is None:
                return default
            return number if isinstance(number, int) else value(number, 'unsignedIntegerValue')

        def interruption(note):
            if self.closed:
                return
            self.active_interruption = notification_number(note, interruption_key, 1) == 1
            interrupted(self.active_interruption)
        def route_changed(note):
            if self.closed:
                return
            number = notification_number(note, route_key, 0)
            changed(lost=number in (2, 7))  # Old output unavailable / no suitable route.
        queue = value(ObjCClass('NSOperationQueue'), 'mainQueue')
        try:
            for name, callback in (
                ('AVAudioSessionRouteChangeNotification', route_changed),
                ('AVAudioSessionInterruptionNotification', interruption),
            ):
                block = Block(callback, None, objc_id)
                token = self.center.addObserverForName(name, object=None, queue=queue, usingBlock=block)
                self.tokens.append((token, block))
        except Exception:
            try:
                self.dispose()
            except Exception:
                logging.getLogger(__name__).error('Could not roll back Apple audio observers.')
            raise

    def prepare(self):
        # Activate without submitting audio, then re-query the actual selected route.
        return bool(self.audio.setCategory('AVAudioSessionCategoryPlayback', error=None)
                    and self.audio.setActive(True, error=None))

    def outputs(self):
        ports = value(value(self.audio, 'currentRoute'), 'outputs')
        result = []
        for port in ports:
            kind = str(value(port, 'portType'))
            uid = value(port, 'UID')
            identity = str(uid) if uid is not None else ''
            if kind in {'Speaker', 'Receiver'}:
                identity = identity or kind
            result.append(output('ios:' + kind, identity, str(value(port, 'portName')),
                                 bluetooth=kind in {'BluetoothA2DPOutput', 'BluetoothHFP', 'BluetoothLE'}))
        return tuple(result) or None

    def in_call(self):
        return self.active_interruption

    def dispose(self):
        self.closed = True
        failure = None
        pending = []
        for token, block in self.tokens:
            try:
                self.center.removeObserver(token)
            except Exception as error:
                pending.append((token, block))
                failure = failure or error
        self.tokens = pending
        if failure is not None:
            raise failure


class AndroidOutputs:
    def __init__(self, app, changed, interrupted):
        from java import jclass, dynamic_proxy
        kind = jclass('io.github.ispaure.logistics.audio.AudioOutputs')
        class Listener(dynamic_proxy(kind.Listener)):
            def changed(self):
                changed()

            def lost(self):
                changed(lost=True)
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
