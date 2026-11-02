"""Desktop lock/sleep, output-loss and display-awake integration."""

import ctypes
import sys
import weakref

from commonUtils.ui import pyside as qt
from PySide6.QtMultimedia import QMediaDevices

_observers = {}
_notification_callback = None


class CocoaNotifications:
    def __init__(self, notify):
        global _notification_callback
        self.objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
        self.objc.objc_getClass.argtypes = [ctypes.c_char_p]
        self.objc.objc_getClass.restype = ctypes.c_void_p
        self.objc.sel_registerName.argtypes = [ctypes.c_char_p]
        self.objc.sel_registerName.restype = ctypes.c_void_p
        self.address = ctypes.cast(self.objc.objc_msgSend, ctypes.c_void_p).value
        name = b'LogisticsVideoLifecycleObserver'
        cls = self.objc.objc_getClass(name)
        if not cls:
            self.objc.objc_allocateClassPair.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
            self.objc.objc_allocateClassPair.restype = ctypes.c_void_p
            cls = self.objc.objc_allocateClassPair(self.objc.objc_getClass(b'NSObject'), name, 0)

            @ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
            def callback(receiver, selector, notification):
                handler = _observers.get(receiver)
                if handler is not None:
                    handler()

            _notification_callback = callback  # The registered ObjC class outlives every video.
            self.objc.class_addMethod.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
            self.objc.class_addMethod(cls, self.selector('interrupted:'), callback, b'v@:@')
            self.objc.objc_registerClassPair.argtypes = [ctypes.c_void_p]
            self.objc.objc_registerClassPair(cls)
        self.observer = self.send(self.send(cls, 'alloc'), 'init')
        _observers[self.observer] = notify
        workspace = self.send(self.objc.objc_getClass(b'NSWorkspace'), 'sharedWorkspace')
        self.centers = [self.send(workspace, 'notificationCenter'),
            self.send(self.objc.objc_getClass(b'NSDistributedNotificationCenter'), 'defaultCenter')]
        for center, names in zip(self.centers, (('NSWorkspaceWillSleepNotification',), ('com.apple.screenIsLocked',))):
            for name in names:
                string = self.send(self.objc.objc_getClass(b'NSString'), 'stringWithUTF8String:',
                    (ctypes.c_char_p,), (name.encode(),))
                self.send(center, 'addObserver:selector:name:object:',
                    (ctypes.c_void_p,) * 4, (self.observer, self.selector('interrupted:'), string, None))

    def selector(self, name):
        return self.objc.sel_registerName(name.encode())

    def send(self, receiver, selector, types=(), values=()):
        function = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, *types)(self.address)
        return function(receiver, self.selector(selector), *values)

    def close(self):
        for center in self.centers:
            self.send(center, 'removeObserver:', (ctypes.c_void_p,), (self.observer,))
        _observers.pop(self.observer, None)
        self.send(self.observer, 'release')


class WindowsNotifications(qt.QAbstractNativeEventFilter):
    def __init__(self, window, notify):
        super().__init__()
        self.window, self.notify = window, notify
        self.hwnd = int(window.winId())
        self.wts = ctypes.WinDLL('Wtsapi32')
        self.wts.WTSRegisterSessionNotification.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.wts.WTSUnRegisterSessionNotification.argtypes = [ctypes.c_void_p]
        self.wts.WTSRegisterSessionNotification(self.hwnd, 0)
        qt.QApplication.instance().installNativeEventFilter(self)

    def nativeEventFilter(self, kind, message):
        from ctypes.wintypes import MSG
        msg = ctypes.cast(int(message), ctypes.POINTER(MSG)).contents
        if msg.message == 0x218 and msg.wParam == 4 or msg.message == 0x2B1 and msg.wParam == 7:
            self.notify()
        return False, 0

    def close(self):
        qt.QApplication.instance().removeNativeEventFilter(self)
        self.wts.WTSUnRegisterSessionNotification(self.hwnd)


class DesktopLifecycle(qt.QObject):
    interrupted = qt.Signal()

    def __init__(self, window):
        super().__init__(window)
        self.window = weakref.ref(window)
        self.closed = False
        self.interrupted.connect(self.pause)
        self.devices = QMediaDevices(self)
        self.output = bytes(QMediaDevices.defaultAudioOutput().id())
        self.devices.audioOutputsChanged.connect(self.outputs_changed)
        self.native = None
        self.rebinding = False
        self.awake = False
        self.assertion = ctypes.c_uint(0)
        if sys.platform == 'darwin':
            self.native = CocoaNotifications(self.interrupted.emit)
        elif sys.platform == 'win32':
            self.native = WindowsNotifications(window, self.interrupted.emit)
            window.installEventFilter(self)
        elif sys.platform.startswith('linux'):
            from PySide6.QtDBus import QDBusConnection
            self.bus = QDBusConnection.systemBus()
            self.bus.connect('org.freedesktop.login1', '/org/freedesktop/login1',
                'org.freedesktop.login1.Manager', 'PrepareForSleep', self, qt.SLOT('sleep(bool)'))
            self.session_bus = QDBusConnection.sessionBus()
            for service, path in (('org.freedesktop.ScreenSaver', '/org/freedesktop/ScreenSaver'),
                                  ('org.gnome.ScreenSaver', '/org/gnome/ScreenSaver')):
                self.session_bus.connect(service, path, service, 'ActiveChanged', self, qt.SLOT('sleep(bool)'))

    @qt.Slot(bool)
    def sleep(self, sleeping):
        if sleeping:
            self.pause()

    def eventFilter(self, watched, event):
        if (sys.platform == 'win32' and not self.closed and not self.rebinding
                and event.type() == qt.QEvent.Type.WinIdChange):
            self.rebinding = True
            try:
                self.native.close()
                self.native = WindowsNotifications(watched, self.interrupted.emit)
            finally:
                self.rebinding = False
        return False

    def pause(self):
        window = self.window()
        if window is not None and not self.closed and not window.closing:
            window.pause_requested()
            window.checkpoint()
            if window.resume_guard is not None:
                window.resume_guard.lock()
            self.keep_awake(False)

    def outputs_changed(self):
        output = bytes(QMediaDevices.defaultAudioOutput().id())
        if self.output and (output != self.output or self.output not in {bytes(row.id()) for row in QMediaDevices.audioOutputs()}):
            self.pause()
        self.output = output

    def keep_awake(self, active):
        if self.awake == active:
            return
        if sys.platform == 'win32':
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | (2 if active else 0))
        elif sys.platform == 'darwin':
            if not hasattr(self, 'power'):
                self.power = ctypes.CDLL('/System/Library/Frameworks/IOKit.framework/IOKit')
                self.cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
                self.cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint]
                self.cf.CFStringCreateWithCString.restype = ctypes.c_void_p
                self.cf.CFRelease.argtypes = [ctypes.c_void_p]
                self.power.IOPMAssertionCreateWithName.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
                self.power.IOPMAssertionRelease.argtypes = [ctypes.c_uint]
            if active:
                strings = [self.cf.CFStringCreateWithCString(None, name, 0x08000100)
                    for name in (b'PreventUserIdleDisplaySleep', b'Logistics video playback')]
                try:
                    if self.power.IOPMAssertionCreateWithName(strings[0], 255, strings[1], ctypes.byref(self.assertion)) != 0:
                        return
                finally:
                    for string in strings:
                        self.cf.CFRelease(string)
            else:
                self.power.IOPMAssertionRelease(self.assertion)
        elif sys.platform.startswith('linux'):
            from PySide6.QtDBus import QDBusArgument, QDBusInterface
            interface = QDBusInterface('org.freedesktop.ScreenSaver', '/org/freedesktop/ScreenSaver',
                'org.freedesktop.ScreenSaver', self.session_bus)
            if active:
                reply = interface.call('Inhibit', 'Logistics', 'Video playback')
                if reply.errorName() or not reply.arguments():
                    return
                self.cookie = reply.arguments()[0]
            else:
                interface.call('UnInhibit', QDBusArgument(self.cookie, qt.QMetaType.Type.UInt))
        self.awake = active

    def close(self):
        if self.closed:
            return
        self.keep_awake(False)
        self.closed = True
        if self.native is not None:
            self.native.close()
        window = self.window()
        if sys.platform == 'win32' and window is not None:
            window.removeEventFilter(self)
        if sys.platform.startswith('linux'):
            self.bus.disconnect('org.freedesktop.login1', '/org/freedesktop/login1',
                'org.freedesktop.login1.Manager', 'PrepareForSleep', self, qt.SLOT('sleep(bool)'))
            for service, path in (('org.freedesktop.ScreenSaver', '/org/freedesktop/ScreenSaver'),
                                  ('org.gnome.ScreenSaver', '/org/gnome/ScreenSaver')):
                self.session_bus.disconnect(service, path, service, 'ActiveChanged', self, qt.SLOT('sleep(bool)'))
