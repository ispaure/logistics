"""Mobile video lifetime, credential policy and encrypted resume checkpoints."""
import asyncio
from pathlib import Path

from features.video.playback import VideoContent, SubtitleContent
from services.documents.video_progress import VideoProgress
from features.video.transport import VideoTransport
from services.access_policy import display_allowed


class MobileVideo:
    def __init__(self, app, content):
        self.app, self.content = app, content
        self.buffer_waits = set()
        self.failure_message = None
        self.transport = VideoTransport(content, waiting=lambda token, active:
            app.loop.call_soon_threadsafe(self.network_waiting, token, active),
            failed=lambda category: app.loop.call_soon_threadsafe(self.stream_failed, category))
        from services.documents.video_state import MobileCipher
        from .controls import PlaybackControls
        self.progress = VideoProgress(content, Path(app.private_root) / 'Video', remote_cipher=MobileCipher(app), app=app)
        self.controls = PlaybackControls(self)
        self.native = None
        self.subtitles = []
        self.closed = False
        self.hidden = False
        self.native_restricted = None
        self.task = None
        self.retirement = None
        self._release_retirement = None
        self.audio_output = app.audio_output
        self.audio_output.register(self, self.pause_audio)
        self.protection = app.protection
        self._release_protection = self.protection.register(self,
            lambda: (getattr(self.content, 'gate', None),),
            protected=lambda: self.content.restricted)

    def network_waiting(self, token, active):
        if active:
            self.buffer_waits.add(token)
        else:
            self.buffer_waits.discard(token)
        if not self.closed and not self.hidden and self.native is not None:
            self.native.network_waiting(bool(self.buffer_waits))

    def stream_failed(self, category):
        messages = {
            'access': 'Video access expired. Unlock the source, then press Play to retry.',
            'changed': 'The video changed while it was open. Close and reopen it.',
            'read': 'Video data could not be read. Check the connection, then press Play to retry.',
            'busy': 'The video connection is busy. Press Play to retry.',
        }
        self.failure_message = messages.get(category, messages['read'])
        if not self.closed and not self.hidden and self.native is not None:
            self.native.transport_failed(self.failure_message)

    def pause_audio(self):
        if self.native is not None:
            self.native.pause()

    def playback_allowed(self, external=False):
        return self.allowed(external) and self.audio_output.permitted()

    def request_play(self):
        if not self.allowed() or not self.audio_output.request_play():
            return False
        self.transport.resume()
        self.failure_message = None
        return True

    def retire(self, *, checkpoint=None):
        """Revoke playback immediately; retain resources until native teardown ends."""
        if self.retirement is not None:
            return self.retirement
        self.closed = True
        self.audio_output.unregister(self)
        if self.task is not None:
            self.task.cancel()
        self.transport.suspend()
        if self._release_retirement is None:
            protected = self.content.restricted or bool(self.native_restricted)
            self._release_retirement = self.protection.process.retain(self,
                lambda: (getattr(self.content, 'gate', None),), protected=lambda: protected)
        # Native disposal closes controls/mutes synchronously, then returns its
        # completion barrier. A failed disposal must retain the source and scope.
        disposal = self.native.dispose() if self.native is not None else None
        self.retirement = self.app.loop.create_task(self._finish_retirement(disposal, checkpoint))
        return self.retirement

    async def _finish_retirement(self, disposal, checkpoint):
        if disposal is not None:
            await asyncio.shield(disposal)
        await self.controls.finish()
        self.native = None
        if checkpoint is not None:
            position, completed = checkpoint
            try:
                await asyncio.to_thread(self.progress.save, position, completed=completed)
            except (OSError, ValueError, PermissionError):
                pass
        await asyncio.to_thread(self.transport.close)
        for subtitle in self.subtitles:
            subtitle.close()
        self.content.close()
        self._release_protection()
        self._release_retirement()
        if getattr(self.app, 'video_player', None) is self:
            self.app.video_player = None
        routes = getattr(self.app, 'routes', None)
        if routes is not None:
            routes.sync_back()

    @property
    def restricted(self):
        return self.content.restricted or self.protection.process.protected()

    def retire_changed_policy(self):
        """Native external-playback controls are fixed for this presentation."""
        if (not self.closed and self.native_restricted is not None
                and self.native_restricted != self.restricted):
            self.retire()  # Reopen under current policy rather than keep a second authority.

    def retire_stale(self):
        self.retire_changed_policy()
        if self.closed:
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
        from features.video.session import FolderQueue
        self.controls.queue = FolderQueue(self.content.path, rows)
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
        import json
        self.native.configure(self.controls.settings.json(), json.dumps(self.controls.queue.rows()))
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
                if not display_allowed(inactive=privacy.inactive, captured=getattr(privacy, 'captured', False),
                        locked=any(gate.locked for gate in privacy.gates())):
                    return False
            self.content.require_external() if external else self.content.check_access()
            return True
        except (OSError, ValueError, PermissionError):
            return False

    async def watch(self):
        checkpoints = 0
        try:
            while not self.closed:
                await asyncio.sleep(1)
                checkpoints += 1
                if self.native is not None and not self.hidden:
                    if not self.allowed():
                        self.native.pause()
                        self.transport.suspend()
                    else:
                        self.transport.resume()
                        self.native.cached_ranges(self.content.buffered_ranges())
                        if checkpoints % 5:
                            continue
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
            self.transport.resume()
            self.hidden = False
            self.native.network_waiting(bool(self.buffer_waits))
            if self.failure_message:
                self.native.transport_failed(self.failure_message)
            self.native.show()  # Authentication restores controls, never autoplay.

    async def close(self):
        checkpoint = None
        if not self.closed and self.native is not None:
            checkpoint = self.native.position()
        # Cancellation of a navigation request must not cancel decoder cleanup.
        await asyncio.shield(self.retire(checkpoint=checkpoint))


async def open_video(app, provider, path):
    if not app.require_feature('video') or not app.checkpoint():
        return False
    previous = getattr(app, 'video_player', None)
    navigation = getattr(app, 'navigation_generation', None)
    content = await asyncio.to_thread(VideoContent, provider, path)
    try:
        if previous is not None:
            await previous.close()
    except BaseException:
        content.close()
        raise
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
        player.native.play()
        progress = getattr(player, 'progress', None)
        state = getattr(progress, 'credential_state', None)
        notice = getattr(progress, 'resume_notice', None)
        if state is not None and state.locked_state:
            notice = 'Saved position needs the previous ZIP password. Use Settings → App → Migrate protected reader history.'
        if notice:
            app.loop.call_later(1, lambda: player.native.status(notice) if not player.closed and player.native is not None else None)
        from services.documents.mobile_storage import remember_video
        try:
            remember_video(app, content)
        except (OSError, ValueError, AttributeError, KeyError):
            manager = getattr(app, 'credential_document_lists', None)
            if manager is not None:
                manager.notice()
        return True
    except BaseException:
        await player.close()
        raise
