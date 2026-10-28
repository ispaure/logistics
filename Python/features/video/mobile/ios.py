"""Rubicon presentation of the native VLCKit video controller."""


def native_value(owner, name):
    value = getattr(owner, name)
    return value() if callable(value) else value


class IOSVideo:
    def __init__(self, owner, position, subtitles):
        import json
        from ctypes import c_bool
        from rubicon.objc import ObjCClass, Block
        self.owner = owner
        self.disposed = False
        self.presentation = None
        self.native = ObjCClass('LGVideoController').alloc().init()
        self.native.videoURL = owner.transport.url
        self.native.startMilliseconds = position
        self.native.restricted = owner.restricted
        self.native.subtitleJSON = json.dumps(subtitles)
        self.allowed = Block(lambda external: owner.playback_allowed(bool(external)), c_bool, c_bool)
        self.request_play = Block(lambda: owner.request_play(), c_bool)
        self.native.requestPlay = self.request_play
        self.closed = Block(lambda: owner.app.loop.create_task(owner.close()), None)
        self.native.allowed = self.allowed
        self.native.closed = self.closed
        self.native.modalPresentationStyle = 0
        self.native.loadViewIfNeeded()
        self.show()

    def position(self):
        return int(self.native.positionMilliseconds()), bool(self.native.completed())

    def pause(self):
        self.native.pause()

    def pause_for_background(self):
        self.native.background()

    def status(self, message):
        self.native.showStatus(message)

    def hide(self):
        if self.presentation is not None:
            self.presentation.cancel()
            self.presentation = None
        self.native.suspendForLock()
        self.native.dismissViewControllerAnimated(False, completion=None)

    def show(self):
        if self.disposed or self.owner.closed or self.owner.hidden or not self.owner.allowed():
            self.presentation = None
            return
        self.presentation = None
        self.native.revealSurface()
        host = self.owner.app.main_window._impl.native.rootViewController
        while host.presentedViewController:
            presented = host.presentedViewController
            if presented == self.native:
                return
            if (native_value(presented, 'isBeingDismissed')
                    or native_value(presented, 'isBeingPresented')):
                self.presentation = self.owner.app.loop.call_later(.05, self.show)
                return
            host = presented
        if native_value(host, 'isBeingDismissed') or native_value(host, 'isBeingPresented'):
            self.presentation = self.owner.app.loop.call_later(.05, self.show)
            return
        host.presentViewController(self.native, animated=False, completion=None)

    async def wait_ready(self):
        import asyncio
        for _ in range(100):
            if self.disposed or self.owner.closed:
                return False
            view = native_value(self.native, 'view')
            if (self.native.player is not None and native_value(view, 'window') is not None
                    and not native_value(self.native, 'isBeingPresented')):
                return True
            await asyncio.sleep(.05)
        raise RuntimeError('Video presentation did not finish. Close and reopen the video.')

    def dispose(self):
        self.disposed = True
        if self.presentation is not None:
            self.presentation.cancel()
            self.presentation = None
        self.native.retire()
        self.native.dismissViewControllerAnimated(False, completion=None)
