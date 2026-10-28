"""Mobile video lifetime, credential policy and encrypted resume checkpoints."""
import asyncio
from pathlib import Path

from features.video.playback import VideoContent, SubtitleContent
from services.documents.video_progress import VideoProgress
from features.video.transport import VideoTransport


class MobileVideo:
    def __init__(self, app, content):
        self.app, self.content = app, content
        self.transport = VideoTransport(content)
        self.progress = VideoProgress(content, Path(app.private_root) / 'Video')
        self.native = None
        self.subtitles = []
        self.closed = False
        self.hidden = False
        self.native_restricted = None
        self.task = None
        self.audio_output = app.audio_output
        self.audio_output.register(self, self.pause_audio)

    def pause_audio(self):
        if self.native is not None:
            self.native.pause()

    def playback_allowed(self, external=False):
        return self.allowed(external) and self.audio_output.permitted()

    def request_play(self):
        return self.allowed() and self.audio_output.request_play()

    def retire(self):
        """Synchronous host shutdown/replacement cannot leave a decoder alive."""
        self.closed = True
        self.audio_output.unregister(self)
        if self.task is not None:
            self.task.cancel()
        if self.native is not None:
            self.native.dispose()
            self.native = None
        self.transport.close()
        for subtitle in self.subtitles:
            subtitle.close()
        self.content.close()
        if getattr(self.app, 'video_player', None) is self:
            self.app.video_player = None
        routes = getattr(self.app, 'routes', None)
        if routes is not None:
            routes.sync_back()

    @property
    def restricted(self):
        privacy = getattr(self.app, 'screen_privacy', None)
        return self.content.restricted or bool(privacy is not None and privacy.gates())

    def retire_stale(self):
        if self.native_restricted is False and self.restricted:
            self.retire()  # A newly loaded session must retire existing external playback.
            return
        try:
            self.content.source.check_access()
        except (OSError, ValueError, PermissionError):
            self.retire()

    def prepare(self):
        position = self.progress.load()
        folder, _, name = self.content.path.rpartition('/')
        stem = Path(name).stem
        try:
            rows = self.content.provider.list(folder)
        except OSError:
            if not self.content.remote:
                raise
            rows = []  # Optional sidecars must not prevent cloud playback.
        external = []
        for row in rows:
            if len(external) >= 32:
                break
            if (not row['directory'] and Path(row['name']).suffix.lower() in SubtitleContent.extensions
                    and (Path(row['name']).stem == stem or row['name'].startswith(stem + '.'))):
                try:
                    subtitle = SubtitleContent(self.content.provider, row['path'])
                except OSError:
                    if not self.content.remote:
                        raise
                    continue
                if subtitle.size > 8 * 1024 * 1024:
                    subtitle.close()
                    continue
                self.subtitles.append(subtitle)
                external.append(dict(name=row['name'], url=self.transport.add_subtitle(subtitle)))
        return position, external

    def present(self, position, external):
        self.native_restricted = self.restricted
        backend = type(self.app._impl).__module__
        if backend.startswith('toga_android.'):
            from .android import AndroidVideo
            self.native = AndroidVideo(self, position, external)
        elif backend.startswith('toga_iOS.'):
            from .ios import IOSVideo
            self.native = IOSVideo(self, position, external)
        else:
            raise ValueError('Native mobile video playback requires Android or iOS.')
        if self.content.remote:
            self.native.status('Cloud streaming may buffer or fail when seeking. Resume lasts while this player is open.')
        self.task = self.app.loop.create_task(self.watch())
        self.app.routes.sync_back()

    def allowed(self, external=False):
        try:
            if self.closed or not self.app.active_host:
                return False
            privacy = getattr(self.app, 'screen_privacy', None)
            if external and self.restricted:
                return False
            if self.restricted and privacy is not None:
                if privacy.inactive or getattr(privacy, 'captured', False) or privacy.saved_content is not None or any(gate.locked for gate in privacy.gates()):
                    return False
            self.content.require_external() if external else self.content.check_access()
            self.transport.resume()
            return True
        except (OSError, ValueError, PermissionError):
            return False

    async def watch(self):
        try:
            while not self.closed:
                await asyncio.sleep(5)
                if self.native is not None and not self.hidden:
                    if not self.allowed():
                        self.native.pause()
                        self.transport.suspend()
                    else:
                        position, completed = self.native.position()
                        try:
                            await asyncio.to_thread(self.progress.save, position, completed=completed)
                        except (OSError, ValueError, PermissionError) as error:
                            self.native.status('Resume unavailable: ' + str(error)[:150])
        except asyncio.CancelledError:
            pass

    def conceal(self):
        if self.closed or self.native is None or self.hidden:
            return
        # Snapshot the native position before the host locks credential gates.
        position, completed = self.native.position()
        self.native.pause_for_background()
        if self.restricted:
            self.transport.suspend()
            self.native.hide()
            self.hidden = True
        async def save():
            try:
                await asyncio.to_thread(self.progress.save, position, completed=completed)
            except (OSError, ValueError, PermissionError):
                pass  # The last durable checkpoint remains; never write plaintext.
        self.app.loop.create_task(save())

    def reveal(self):
        if self.hidden and self.allowed():
            self.hidden = False
            self.native.show()  # Authentication restores controls, never autoplay.

    async def close(self):
        if self.closed:
            return
        self.closed = True
        self.audio_output.unregister(self)
        if self.task is not None:
            self.task.cancel()
        try:
            if self.native is not None:
                position, completed = self.native.position()
                self.native.dispose()
                try:
                    await asyncio.to_thread(self.progress.save, position, completed=completed)
                except (OSError, ValueError, PermissionError):
                    pass
        finally:
            await asyncio.to_thread(self.transport.close)
            self.native = None
            self.retire()


async def open_video(app, provider, path):
    if not app.require_feature('video') or not app.checkpoint():
        return False
    previous = getattr(app, 'video_player', None)
    if previous is not None:
        await previous.close()
    navigation = getattr(app, 'navigation_generation', None)
    content = await asyncio.to_thread(VideoContent, provider, path)
    try:
        player = MobileVideo(app, content)
    except BaseException:
        content.close()
        raise
    try:
        position, subtitles = await asyncio.to_thread(player.prepare)
        if (not app.active_host or not player.allowed()
                or getattr(app, 'navigation_generation', None) != navigation):
            await player.close()
            return False
        app.video_player = player
        player.present(position, subtitles)
        ready = getattr(player.native, 'wait_ready', None)
        if ready is not None and not await ready():
            await player.close()
            return False
        if (not app.active_host or player.closed or not player.allowed()
                or getattr(app, 'navigation_generation', None) != navigation):
            await player.close()
            return False
        return True
    except BaseException:
        await player.close()
        raise
