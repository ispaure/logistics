"""Thin Chaquopy binding to the feature-owned Android VLC surface."""
import json


class AndroidVideo:
    def __init__(self, owner, position, subtitles):
        from java import jclass, dynamic_proxy
        self.owner = owner
        Listener = jclass('io.github.ispaure.logistics.video.VideoPlayer$Listener')

        class Callbacks(dynamic_proxy(Listener)):
            def controlInsets(self, metrics):
                from commonUtils.ui.readers.layout import overlay_insets
                values = json.loads(str(metrics))
                return json.dumps(overlay_insets(**values))

            def allowed(self, external):
                return owner.playback_allowed(bool(external))

            def requestPlay(self):
                return owner.request_play()

            def command(self, name, value):
                owner.controls.dispatch(name, value)

            def closed(self):
                owner.app.loop.call_soon_threadsafe(lambda: owner.app.loop.create_task(owner.close()))

        self.callbacks = Callbacks()
        self.native = jclass('io.github.ispaure.logistics.video.VideoPlayer')(
            owner.app._impl.native, owner.transport.url, position,
            owner.restricted, json.dumps(subtitles), self.callbacks)
        self.native.show()

    def configure(self, settings, queue):
        from .controls import native_options
        self.native.configurePlayback(native_options(settings, self.owner.content), queue)

    def seek(self, position):
        self.native.seekTo(position)

    def add_subtitle(self, url):
        self.native.attachSubtitleURL(url)

    def subtitle_browser(self, entries):
        self.native.showSubtitleBrowser(entries)

    def cached_ranges(self, value):
        self.native.showCachedRanges(json.dumps(value))

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
        done = self.owner.app.loop.create_future()
        done.set_result(None)
        return done
