"""Mobile video lifetime, credential policy and encrypted resume checkpoints."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING

from features.video.playback import VideoContent, SubtitleContent
from services.documents.video_progress import VideoProgress
from features.video.transport import VideoTransport
from services.worker_retirement import drain_worker
from services.access_policy import display_allowed

if TYPE_CHECKING:
    from .mkv import MKVStream


@dataclass
class _AirPlayPreparation:
    """Resources owned by one preparation until native accepts its stream."""
    cancel: Event = field(default_factory=Event)
    stream: 'MKVStream | None' = None


class MobileVideo:
    def __init__(self, app, content):
        self.app, self.content = app, content
        self.buffer_waits = set()
        self.failure_message = None
        from services.documents.video_state import MobileCipher
        from .controls import PlaybackControls
        self.native = None
        self.subtitles = []
        self.closed = False
        self.hidden = False
        self.native_restricted = None
        self.task = None
        self.retirement = None
        self.progress_workers = set()
        self.last_sample = None
        self.discovery = None
        self.mkv_stream = None
        self.cancel_remux = None
        self.switching_player = False
        self._release_retirement = None
        self.audio_output = app.audio_output
        self.opening_play_context = None
        self.protection = app.protection
        # Until construction succeeds, unwind every acquired handle locally.
        # open_video still owns and closes content on construction failure.
        with ExitStack() as opening:
            self.transport = VideoTransport(content, waiting=lambda token, active:
                app.loop.call_soon_threadsafe(self.network_waiting, token, active),
                failed=lambda category: app.loop.call_soon_threadsafe(self.stream_failed, category))
            opening.callback(self.transport.close)
            self.progress = VideoProgress(content, Path(app.private_root) / 'Video', remote_cipher=MobileCipher(app), app=app)
            self.controls = PlaybackControls(self)
            self.audio_output.register(self, self.pause_audio,
                continues_after_display_disconnect=self.continues_after_display_disconnect)
            opening.callback(self.audio_output.unregister, self)
            self._release_protection = self.protection.register(self,
                lambda: (getattr(self.content, 'gate', None),),
                protected=lambda: self.content.restricted)
            opening.pop_all()

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

    def continues_after_display_disconnect(self):
        from .ios import IOSVideo
        return (not self.closed and isinstance(self.native, IOSVideo)
                and self.native.continues_after_display_disconnect())

    def playback_allowed(self, external=False):
        return self.allowed(external) and self.audio_output.permitted()

    def request_play(self):
        if not self.allowed() or not self.audio_output.request_play(context=self.opening_play_context):
            return False
        self.transport.resume()
        self.failure_message = None
        return True

    def retire(self):
        """Revoke playback immediately; retain resources until native teardown ends."""
        if self.retirement is not None:
            return self.retirement
        # Sample a TV session even when the user dismisses it between watch ticks.
        from .ios import IOSVideo
        if isinstance(self.native, IOSVideo) and self.native.airplay_active() and self.allowed():
            try:
                self.accept_sample(*self.native.progress_position())
            except (OSError, ValueError):
                pass  # Keep the last checkpoint if the source changed as it closed.
        self.closed = True
        if self.cancel_remux is not None:
            self.cancel_remux.set()
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
        self.retirement = self.app.loop.create_task(self._finish_retirement(disposal))
        return self.retirement

    async def _finish_retirement(self, disposal):
        # Native teardown and tracked commands may still use the source or a
        # provisional AirPlay stream. Drain them before releasing retained media.
        if disposal is not None:
            await asyncio.shield(disposal)
        if self.discovery is not None:
            await asyncio.shield(self.discovery)
        await self.controls.finish()
        await self.release_airplay_stream()
        self.native = None
        # Checkpoints need the provider and protection scopes until the last
        # write finishes, even after playback and its streams have stopped.
        for worker in tuple(self.progress_workers):
            await drain_worker(worker)
        try:
            await self.flush_progress()
        except (OSError, ValueError):
            pass
        self.progress.retire()
        await asyncio.to_thread(self.transport.close)
        for subtitle in self.subtitles:
            subtitle.close()
        self.content.close()
        # Release protection only after every source consumer has retired.
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

    def prepare_media_bounds(self):
        from dataclasses import asdict
        from features.video.chapters import read_media_bounds
        bounds = read_media_bounds(self.content, cancelled=lambda: self.closed)
        self.content.check_access()
        if not self.closed:
            self.content.media_bounds = {**asdict(bounds), 'end_ms': bounds.end_ms}

    def prepare(self):
        if not self.content.remote:
            self.prepare_media_bounds()
        position = self.progress.load()
        end = (self.content.media_bounds or {}).get('end_ms')
        if end is not None:
            position = min(position, max(0, end - 1))
        self.controls.settings = self.controls.store.load()
        # Remote directory enumeration and optional sidecar stats must not sit
        # in front of the first video request. Keep the retained source until
        # background discovery finishes, including when the viewer closes.
        return position, [] if self.content.remote else self.prepare_sidecars()

    def prepare_sidecars(self):
        if self.content.remote and self.content.media_bounds is None:
            self.prepare_media_bounds()
        folder = self.content.path.rpartition('/')[0]
        try:
            rows = self.content.provider.list(folder)
        except OSError:
            if not self.content.remote:
                raise
            rows = []  # Optional sidecars must not prevent cloud playback.
        from features.video.session import FolderQueue
        self.controls.queue = FolderQueue(self.content.path, rows)
        from features.video.sidecars import discover_sidecars
        saved = getattr(getattr(self.controls, 'settings', None), 'subtitle_file', '')
        resources = discover_sidecars(self.content, cancelled=lambda: self.closed,
            preferred=saved if isinstance(saved, str) else '', entries=rows)
        external = []
        try:
            for subtitle in resources:
                external.append(dict(name=Path(subtitle.path).name, url=self.transport.add_subtitle(subtitle)))
                self.subtitles.append(subtitle)
        finally:
            for subtitle in resources:
                if subtitle not in self.subtitles:
                    subtitle.close()
        return external

    def restore_subtitle(self, external):
        saved = self.controls.settings.subtitle_file
        if saved and self.native is not None:
            selected = next((row for row in external if row['name'] == Path(saved).name), None)
            if selected:
                self.native.add_subtitle(selected['url'])

    async def discover_sidecars(self):
        try:
            external = await asyncio.to_thread(self.prepare_sidecars)
            if not self.closed and self.native is not None and self.allowed():
                import json
                self.native.configure(self.controls.settings.json(), json.dumps(self.controls.queue.rows()))
                self.restore_subtitle(external)
        except (OSError, ValueError):
            pass  # Optional discovery must not interrupt an already playing video.

    def present(self, position, external, *, fullscreen=False):
        self.native_restricted = self.restricted
        backend = type(self.app._impl).__module__
        if backend.startswith('toga_android.'):
            from .android import AndroidVideo
            self.native = AndroidVideo(self, position, external, fullscreen=fullscreen)
        elif backend.startswith('toga_iOS.'):
            from .ios import IOSVideo
            self.native = IOSVideo(self, position, external)
            self.native.present()
        else:
            raise ValueError('Native mobile video playback requires Android or iOS.')
        import json
        self.native.configure(self.controls.settings.json(), json.dumps(self.controls.queue.rows()))
        self.restore_subtitle(external)
        self.last_sample = (position, False)
        if self.progress.resume_notice:
            self.native.status(self.progress.resume_notice)
        self.task = self.app.loop.create_task(self.watch())
        self.app.routes.sync_back()

    async def prepare_airplay(self):
        from .ios import airplay_file

        if self.closed or self.switching_player:
            return
        if not self.allowed(external=True):
            self.native.airplay_preparation_failed('AirPlay is unavailable for this video.')
            return
        self.switching_player = True
        provisional = _AirPlayPreparation()
        try:
            if self.native.airplay_active():
                return
            await self.release_airplay_stream()
            if self.closed:
                return
            path = airplay_file(self)
            if path is None:
                raise ValueError('AirPlay is unavailable for this video.')
            await self._prepare_airplay_stream(path, provisional)
            # Remux preparation can outlive access or this presentation. Native
            # acceptance is the ownership boundary, after fresh authorization.
            if self.closed:
                return
            if not self.allowed(external=True):
                raise ValueError('AirPlay is unavailable for this video.')
            self.content.check()
            if self.native.start_airplay(path, provisional.stream):
                self.mkv_stream, provisional.stream = provisional.stream, None
            else:
                self.native.airplay_preparation_failed('Choose a TV in AirPlay to start streaming.')
        except (OSError, ValueError, NameError) as error:
            if not self.closed:
                self.native.airplay_preparation_failed(str(error) or 'AirPlay could not prepare this video.')
        finally:
            try:
                if provisional.stream is not None:
                    await self._discard_airplay_stream(provisional.stream)
            finally:
                self.cancel_remux = None
                self.switching_player = False

    async def _prepare_airplay_stream(self, path: Path, provisional: _AirPlayPreparation):
        """Recover every worker result into the caller's cleanup scope."""
        from .mkv import MKVStream, UnsupportedAirPlayMedia

        if path.suffix.lower() not in {'.mkv', '.mp4', '.m4v', '.mov'}:
            return None
        self.native.status('Preparing AirPlay…')
        self.cancel_remux = provisional.cancel
        preparation = self.app.loop.create_task(asyncio.to_thread(
            MKVStream, self, path, provisional.cancel))
        try:
            provisional.stream = await asyncio.shield(preparation)
        except UnsupportedAirPlayMedia:
            # AVFoundation can play wider MP4/MOV profiles with embedded text
            # tracks. MKV requires remuxing; other failures never opt into fallback.
            if path.suffix.lower() == '.mkv':
                raise
            return None
        except asyncio.CancelledError:
            provisional.cancel.set()
            await drain_worker(preparation)
            if not preparation.cancelled() and preparation.exception() is None:
                provisional.stream = preparation.result()
            raise

    async def _discard_airplay_stream(self, stream):
        """Finish provisional cleanup before propagating preparation cancellation."""
        worker = self.app.loop.create_task(asyncio.to_thread(stream.close))
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            await drain_worker(worker)
            worker.result()
            raise

    async def release_airplay_stream(self):
        # Detach the retained stream once; this coroutine owns its close barrier.
        stream, self.mkv_stream = self.mkv_stream, None
        if stream is not None:
            worker = self.app.loop.create_task(asyncio.to_thread(stream.close))
            await drain_worker(worker)
            worker.result()

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

    async def flush_progress(self, observation=None):
        worker = self.app.loop.create_task(asyncio.to_thread(self.progress.flush, observation))
        self.progress_workers.add(worker)
        worker.add_done_callback(self.progress_workers.discard)
        try:
            status = await asyncio.shield(worker)
            if status == 'locked' and not self.closed and not self.hidden and self.native is not None:
                self.native.status(self.progress.resume_notice)
            return status
        except asyncio.CancelledError:
            await drain_worker(worker)
            raise

    def accept_sample(self, position, completed=False):
        sample = position, completed
        if position < 0 or sample == self.last_sample:
            return None
        observation = self.progress.observe(position, completed=completed)
        self.last_sample = sample
        return observation

    async def watch(self):
        checkpoints = 0
        try:
            while not self.closed:
                await asyncio.sleep(1)
                checkpoints += 1
                if self.native is not None and not self.hidden:
                    diagnostics = getattr(self.native, 'refresh_display_diagnostics', None)
                    if diagnostics is not None:
                        diagnostics()
                    if not self.allowed():
                        self.native.pause()
                        self.transport.suspend()
                    else:
                        self.transport.resume()
                        self.native.cached_ranges(self.content.buffered_ranges())
                        try:
                            sample = self.native.progress_position()
                            self.accept_sample(*sample)
                            if checkpoints % 5 == 0 or sample[1]:
                                await self.flush_progress()
                        except (OSError, ValueError) as error:
                            if not self.closed and not self.hidden and self.native is not None:
                                self.native.status('Resume unavailable: ' + str(error)[:150])
        except asyncio.CancelledError:
            pass

    def conceal(self):
        if self.closed or self.native is None or self.hidden:
            return
        self.native.pause_for_background()
        if self.restricted:
            self.transport.suspend()
            self.native.hide()
            self.hidden = True
        async def save():
            try:
                await self.flush_progress()
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
        # Cancellation of a navigation request must not cancel decoder cleanup.
        await asyncio.shield(self.retire())


async def open_video(app, provider, path, *, fullscreen=False, continuation=False):
    if not app.require_feature('video') or not app.checkpoint():
        return False
    previous = getattr(app, 'video_player', None)
    navigation = getattr(app, 'navigation_generation', None)
    play_context = app.audio_output.play_context()
    acquisition = asyncio.create_task(asyncio.to_thread(VideoContent, provider, path))
    try:
        content = await asyncio.shield(acquisition)
    except asyncio.CancelledError:
        await drain_worker(acquisition)
        if not acquisition.cancelled() and acquisition.exception() is None:
            try:
                acquisition.result().close()
            except Exception as error:
                asyncio.get_running_loop().call_exception_handler(
                    dict(message='Could not close cancelled video source', exception=error))
        raise
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
        preparation = asyncio.create_task(asyncio.to_thread(player.prepare))
        try:
            position, subtitles = await asyncio.shield(preparation)
        except asyncio.CancelledError:
            await drain_worker(preparation)
            raise
        if (not app.active_host or not player.allowed()
                or getattr(app, 'navigation_generation', None) != navigation):
            await player.close()
            return False
        app.video_player = player
        player.present(position, subtitles, fullscreen=fullscreen)
        ready = getattr(player.native, 'wait_ready', None)
        if ready is not None and not await ready():
            await player.close()
            return False
        if (not app.active_host or player.closed or not player.allowed()
                or getattr(app, 'navigation_generation', None) != navigation):
            await player.close()
            return False
        # Native startByUser calls request_play synchronously. Bind the initial
        # request to the selection before provider I/O and modal presentation.
        if not continuation or app.audio_output.permitted():
            player.opening_play_context = play_context
            try:
                player.native.play()
            finally:
                player.opening_play_context = None
        if content.remote:
            player.discovery = asyncio.create_task(player.discover_sidecars())
        progress = getattr(player, 'progress', None)
        state = getattr(progress, 'credential_state', None)
        notice = getattr(progress, 'resume_notice', None)
        if state is not None and state.locked_state:
            notice = 'Saved position needs the previous ZIP password. Use Settings → Workspaces → Migrate protected reader history.'
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
    except BaseException as opening_error:
        cleanup = asyncio.create_task(player.close())
        if isinstance(opening_error, asyncio.CancelledError):
            await drain_worker(cleanup)
            if not cleanup.cancelled() and (error := cleanup.exception()) is not None:
                asyncio.get_running_loop().call_exception_handler(
                    dict(message='Could not retire cancelled video opening', exception=error))
        else:
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await drain_worker(cleanup)
                raise
        raise
