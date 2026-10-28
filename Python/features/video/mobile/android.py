"""Thin Chaquopy binding to the feature-owned Android VLC surface."""
import json


class AndroidVideo:
    def __init__(self, owner, position, subtitles):
        from java import jclass, dynamic_proxy
        self.owner = owner
        Listener = jclass('io.github.ispaure.logistics.video.VideoPlayer$Listener')

        class Callbacks(dynamic_proxy(Listener)):
            def allowed(self, external):
                return owner.playback_allowed(bool(external))

            def requestPlay(self):
                return owner.request_play()

            def closed(self):
                owner.app.loop.call_soon_threadsafe(lambda: owner.app.loop.create_task(owner.close()))

        self.callbacks = Callbacks()
        self.native = jclass('io.github.ispaure.logistics.video.VideoPlayer')(
            owner.app._impl.native, owner.transport.url, position,
            owner.restricted, json.dumps(subtitles), self.callbacks)
        self.native.show()

    def pause(self):
        self.native.pause()

    def pause_for_background(self):
        self.native.background()

    def position(self):
        return int(self.native.position()), bool(self.native.completed())

    def status(self, message):
        self.native.status(message)

    def hide(self):
        self.native.hide()

    def show(self):
        self.native.show()

    def dispose(self):
        self.native.dispose()
