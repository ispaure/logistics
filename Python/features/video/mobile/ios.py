"""Rubicon presentation of the iOS video controllers."""

from pathlib import Path


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
        self.display = getattr(getattr(owner.app, 'scene_manager', None), 'external_comics', None)
        self.display_registration = None
        self.native = ObjCClass('LGVideoController').alloc().init()
        self.native.videoURL = owner.transport.url
        self.native.startMilliseconds = position
        self.native.knownDuration = owner.progress.duration
        self.native.restricted = owner.restricted
        self.native.airPlayAvailable = airplay_file(owner) is not None
        self.airplay_allowed = Block(self.airplay_source_allowed, c_bool)
        self.native.airPlayAllowed = self.airplay_allowed
        self.native.subtitleJSON = json.dumps(subtitles)
        self.allowed = Block(lambda external: owner.playback_allowed(bool(external)), c_bool, c_bool)
        self.request_play = Block(lambda: owner.request_play(), c_bool)
        self.native.requestPlay = self.request_play
        self.closed = Block(lambda: owner.app.loop.create_task(owner.close()), None)
        self.native.allowed = self.allowed
        self.native.closed = self.closed
        self.external_display_allowed = Block(lambda: self.display is not None
            and self.display.allowed_host(owner.app) and owner.allowed(external=True), c_bool)
        self.native.externalDisplayAllowed = self.external_display_allowed
        if self.display is not None:
            self.output_changed = Block(lambda: owner.app.loop.call_soon_threadsafe(self.display.refresh), None)
            self.native.externalOutputChanged = self.output_changed
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

    def present(self):
        if self.display is not None:
            self.display.select(self.owner.app)
        self.show()

    def set_external_display(self, view):
        return bool(self.native.moveVideoToExternalHost(view))

    def external_display_diagnostics(self):
        import json
        return json.loads(str(self.native.externalDisplayDiagnosticJSON()))

    def refresh_display_diagnostics(self):
        if self.display is not None:
            self.display.diagnose_ios()

    def revoke_external_display(self):
        self.native.revokeExternalVideo()

    def disconnect_external_display(self):
        self.native.externalDisplayDisconnected()

    def continues_after_display_disconnect(self):
        return bool(self.native.continuesAfterDisplayDisconnect())

    def airplay_source_allowed(self):
        if not self.owner.allowed(external=True):
            return False
        try:
            self.owner.content.check()
        except (OSError, ValueError):
            return False
        return True

    def airplay_active(self):
        return bool(self.native.hasAirPlay())

    def start_airplay(self, path, stream):
        from rubicon.objc import ObjCClass
        app = self.owner.app
        player = getattr(app, 'video_airplay_player', None)
        if player is None or int(native_value(player, 'status')) == 2:  # AVPlayerStatusFailed
            player = app.video_airplay_player = ObjCClass('AVPlayer').alloc().init()
        url = ObjCClass('NSURL')
        source = url.URLWithString(stream.url) if stream else url.fileURLWithPath(str(path))
        return bool(self.native.beginAirPlay(player, URL=source, title=path.name))

    def airplay_preparation_failed(self, message):
        self.native.airPlayPreparationFailed(message)

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

    def progress_position(self):
        self.owner.progress.duration = int(self.native.durationMilliseconds())
        return int(self.native.progressPosition()), bool(self.native.completed())

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
        self.dismiss()

    def dismiss(self):
        # Dismiss the video and any alert or menu presented above it together.
        presenter = self.container.presentingViewController
        if presenter is not None and presenter.presentedViewController == self.container:
            presenter.dismissViewControllerAnimated(False, completion=None)
        registration = getattr(self, 'display_registration', None)
        if registration is not None:
            self.container.unregisterSceneAccessory(registration)
            self.display_registration = None

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
        if self.display is not None and self.display_registration is None:
            self.display_registration = self.display.register_ios_controller(self.container)
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
        self.dismiss()
        if self.display is not None:
            self.display.refresh()
        return self.disposal


def airplay_file(owner):
    """Resolve a direct file URL only for ordinary, unmapped local storage."""
    from services.documents.progress_identity import ordinary_local_provider

    content = owner.content
    if (owner.app.preferences.values.get('native_video_airplay') != 'true'
            or Path(content.path).suffix.lower() not in {'.mp4', '.mov', '.m4v', '.mkv'}
            or content.remote or not owner.allowed(external=True)):
        return None
    provider = content.provider
    if content.source.backend is not None or ordinary_local_provider(provider) is not provider:
        return None
    try:
        path = provider.local_move_path(content.path)
        content.check()
        return path
    except (OSError, ValueError):
        return None
