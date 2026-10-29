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
        self.disposal = None
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
        from rubicon.objc import objc_id, ObjCInstance
        self.command = Block(lambda name, value: owner.controls.dispatch(str(ObjCInstance(name)), str(ObjCInstance(value))), None, objc_id, objc_id)
        self.native.command = self.command
        from .controls import native_options
        self.native.optionsJSON = native_options(owner.controls.settings.json(), owner.content)
        self.container = ObjCClass('LGVideoNavigationController').alloc().initWithRootViewController(self.native)
        self.container.modalPresentationStyle = 0
        self.container.overrideUserInterfaceStyle = 2
        self.container.view.backgroundColor = native_value(ObjCClass('UIColor'), 'blackColor')
        self.container.navigationBar.tintColor = native_value(ObjCClass('UIColor'), 'whiteColor')
        self.native.loadViewIfNeeded()
        self.show()

    def configure(self, settings, queue):
        from .controls import native_options
        self.native.configurePlayback(native_options(settings, self.owner.content), queue=queue)

    def seek(self, position):
        self.native.seekToMilliseconds(position)

    def add_subtitle(self, url):
        self.native.attachSubtitleURL(url)

    def subtitle_browser(self, entries):
        self.native.showSubtitleBrowser(entries)

    def cached_ranges(self, value):
        import json
        self.native.showCachedRanges(json.dumps(value))

    def position(self):
        return int(self.native.positionMilliseconds()), bool(self.native.completed())

    def network_waiting(self, waiting):
        self.native.setNetworkWaiting(waiting)

    def transport_failed(self, message):
        self.native.setTransportFailure(message)

    def play(self):
        self.native.startByUser()

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
        self.container.dismissViewControllerAnimated(False, completion=None)

    def show(self):
        if self.disposed or self.owner.closed or self.owner.hidden or not self.owner.allowed():
            self.presentation = None
            return
        self.presentation = None
        self.native.revealSurface()
        host = self.owner.app.main_window._impl.native.rootViewController
        while host.presentedViewController:
            presented = host.presentedViewController
            if presented == self.container:
                return
            if (native_value(presented, 'isBeingDismissed')
                    or native_value(presented, 'isBeingPresented')):
                self.presentation = self.owner.app.loop.call_later(.05, self.show)
                return
            host = presented
        if native_value(host, 'isBeingDismissed') or native_value(host, 'isBeingPresented'):
            self.presentation = self.owner.app.loop.call_later(.05, self.show)
            return
        host.presentViewController(self.container, animated=False, completion=None)

    async def wait_ready(self):
        import asyncio
        for _ in range(100):
            if self.disposed or self.owner.closed:
                return False
            view = native_value(self.native, 'view')
            if (self.native.player is not None and native_value(view, 'window') is not None
                    and not native_value(self.container, 'isBeingPresented')):
                return True
            await asyncio.sleep(.05)
        raise RuntimeError('Video presentation did not finish. Close and reopen the video.')

    def dispose(self):
        if self.disposal is not None:
            return self.disposal
        from rubicon.objc import Block
        loop = self.owner.app.loop
        done = self.disposal = loop.create_future()
        self.disposed = True
        if self.presentation is not None:
            self.presentation.cancel()
            self.presentation = None
        def finished():
            # Complete after returning across the ObjC block bridge.
            loop.call_soon_threadsafe(done.set_result, None)
        self.retirement_callback = Block(finished, None)
        try:
            self.native.retireWithCompletion(self.retirement_callback)
        except BaseException:
            self.disposal = None
            raise
        self.container.dismissViewControllerAnimated(False, completion=None)
        return self.disposal
