"""LibVLC decoder adapted to the desktop player's Qt event/track contract."""

import ctypes
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from commonUtils.ui import pyside as qt
from PySide6.QtMultimedia import QMediaPlayer, QMediaMetaData

from .backend import (
    AUDIO_SWITCH_ERROR, AUDIO_SWITCH_TIMEOUT, SEEK_ERROR, SEEK_TIMEOUT, VIDEO_WITHOUT_AUDIO, PlaybackCapabilities,
)


@dataclass
class AudioSwitch:
    track: int
    position: int
    deadline: float | None


@dataclass
class AudioSeek:
    track: int
    position: int
    buffering: bool = False
    buffered: bool = False
    played: int | None = None
    decoded_audio: int | None = None
    decoded_video: int | None = None
    observed_audio_at: float = 0


@dataclass
class OutputObservation:
    position: int
    decoded_audio: int
    played_audio: int
    decoded_video: int
    displayed_video: int
    audio_changed: float
    video_changed: float


class NativeMediaTrack(ctypes.Structure):
    # libvlc_media_track_t has ONE union pointer. The pinned generated Python
    # binding incorrectly lays out audio/video/subtitle as three pointers.
    _fields_ = [('codec', ctypes.c_uint32), ('original_fourcc', ctypes.c_uint32),
        ('id', ctypes.c_int), ('type', ctypes.c_int), ('profile', ctypes.c_int),
        ('level', ctypes.c_int), ('payload', ctypes.c_void_p), ('bitrate', ctypes.c_uint),
        ('language', ctypes.c_char_p), ('description', ctypes.c_char_p)]


def instance_for(vlc, scale=1.0):
    from services.video_runtime import decoder_instance
    instance = decoder_instance(vlc, ('--quiet', '--ignore-config', '--no-media-library',
        '--no-metadata-network-access', '--no-lua', '--no-video-title-show',
        '--no-snapshot-preview', '--audio-filter=scaletempo', '--avcodec-hw=any',
        f'--freetype-rel-fontsize={round(16 / scale)}'))
    if instance is None:
        raise RuntimeError('The LibVLC runtime could not initialize its plugins.')
    return instance


class VLCAudio(qt.QObject):
    mutedChanged = qt.Signal(bool)

    def __init__(self, player, parent):
        super().__init__(parent)
        self.player = player
        self.level, self.muted = .8, False
        self.suppressed = False
        self.closed = False

    def setVolume(self, value):
        self.level = max(0., min(1., value))
        if not self.closed:
            self.player.audio_set_volume(round(self.level * 100))

    def volume(self):
        return self.level

    def setMuted(self, muted):
        muted = bool(muted)
        if not self.closed:
            self.player.audio_set_mute(muted or self.suppressed)
        if self.muted != muted:
            self.muted = muted
            self.mutedChanged.emit(muted)

    def isMuted(self):
        return self.muted

    def suppress(self, suppressed):
        self.suppressed = suppressed
        if not self.closed:
            self.player.audio_set_mute(suppressed or self.muted)


class VLCPlayer(qt.QObject):
    positionChanged = qt.Signal(int)
    durationChanged = qt.Signal(int)
    tracksChanged = qt.Signal()
    mediaStatusChanged = qt.Signal(object)
    playbackStateChanged = qt.Signal(object)
    errorOccurred = qt.Signal()
    picture = qt.Signal(object, object)
    renderedProgress = qt.Signal()
    audioProgress = qt.Signal()
    audioOnlyChanged = qt.Signal(bool)
    videoOnlyChanged = qt.Signal(bool)
    audioSwitchChanged = qt.Signal(bool, str)
    PlaybackState = QMediaPlayer.PlaybackState
    Error = QMediaPlayer.Error
    MediaStatus = QMediaPlayer.MediaStatus

    def __init__(self, vlc, instance, video, parent):
        super().__init__(parent)
        self.vlc, self.instance, self.video = vlc, instance, video
        self.native = instance.media_player_new()
        self.media = None
        self.retired = False
        self.generation = 0
        self.seek_generation = 0
        self._state = self.PlaybackState.StoppedState
        self._error = self.Error.NoError
        self._position = self._duration = 0
        self._tracks = ((), ())
        self._pending_seek = None
        self._seek_issued = False
        self._seek_target = self._seek_deadline = None
        self._seek_error = self._audio_only = self._seek_has_audio_and_video = self._completed = False
        self._clock_observation = None
        self._video_tail_audio = None
        self._end_observation = None
        self._last_audio_track = None
        self._played_audio = 0
        self._audio_switch = self._audio_seek = None
        self._paused_preview_target = None
        self._rate = 1.
        self._options = {}
        self._source = qt.QUrl()
        self._settings = None
        self._pause_after_open = False
        self._buffers = {}
        self._buffer_lock = Lock()
        self._format = None
        self._picture_pending = False
        self._held_position = None
        self._slaves = []
        self._restore_audio_track = self._restore_subtitle_track = None
        self._external_route = False
        self._embedded_subtitles = None
        self._software_subtitles = False
        self._source_size = None
        self._languages = {}
        self._audio_info = {}
        self._font_scale = 1.0
        self._opened = False
        self.presentation_current = False
        self.stats = vlc.MediaStats()
        self._displayed = 0
        self.audio = VLCAudio(self.native, parent)
        self._callbacks = self.make_callbacks()
        self.native.video_set_callbacks(*self._callbacks[:3], None)
        self.native.video_set_format_callbacks(self._callbacks[3], self._callbacks[4])
        self._events = self.native.event_manager()
        self._events.event_attach(vlc.EventType.MediaPlayerBuffering, self.audio_switch_buffering)
        self.picture.connect(self.present_picture)
        self.timer = qt.QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    def make_callbacks(self):
        vlc = self.vlc
        # c_char_p converts a writable four-byte chroma pointer into bytes; use
        # the ABI-equivalent void pointer so the setup callback can write it.
        setup_type = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_void_p, *([ctypes.POINTER(ctypes.c_uint)] * 4))

        @setup_type
        def setup(opaque, chroma, width, height, pitches, lines):
            if not 0 < width[0] <= 8192 or not 0 < height[0] <= 8192:
                return 0
            ctypes.memmove(chroma, b'RV32', 4)
            pitch = (width[0] * 4 + 31) & ~31
            pitches[0], lines[0] = pitch, (height[0] + 31) & ~31
            self._format = width[0], height[0], pitch, lines[0]
            self._source_size = None
            return 1

        @vlc.CallbackDecorators.VideoLockCb
        def lock(opaque, planes):
            width, height, pitch, lines = self._format
            buffer = ctypes.create_string_buffer(pitch * lines + 31)
            address = (ctypes.addressof(buffer) + 31) & ~31
            with self._buffer_lock:
                self._buffers[address] = (buffer, width, height, pitch,
                    (self.generation, self.seek_generation, self._pending_seek is None))
            planes[0] = address
            return address

        @vlc.CallbackDecorators.VideoUnlockCb
        def unlock(opaque, picture, planes):
            pass

        @vlc.CallbackDecorators.VideoDisplayCb
        def display(opaque, picture):
            with self._buffer_lock:
                value = self._buffers.pop(picture, None)
                pending = self._picture_pending
                if value is not None and not pending:
                    self._picture_pending = True
            if value is not None and not self.retired and not pending:
                buffer, width, height, pitch, generation = value
                offset = int(picture) - ctypes.addressof(buffer)
                # Copy while this native picture still belongs to the callback.
                pixels = memoryview(buffer).cast('B')[offset:offset + pitch * height]
                image = qt.QImage(pixels, width, height, pitch, qt.QImage.Format.Format_RGB32).copy()
                self.picture.emit(image, generation)

        @vlc.CallbackDecorators.VideoCleanupCb
        def cleanup(opaque):
            with self._buffer_lock:
                self._buffers.clear()

        return lock, unlock, display, setup, cleanup

    def present_picture(self, image, generation):
        with self._buffer_lock:
            self._picture_pending = False
        preview = (self._paused_preview_target is not None
            and abs(self.native.get_time() - self._paused_preview_target) <= 200) if not self.retired else False
        current = generation[:2] == (self.generation, self.seek_generation)
        if (not self.retired and self.media is not None and current
                and self._error == self.Error.NoError
                and ((self._state == self.PlaybackState.PlayingState and generation[2]) or preview)):
            if self._source_size is None:
                self.read_metadata()
            if self._source_size is not None and image.size() != self._source_size:
                image = image.scaled(self._source_size, qt.Qt.AspectRatioMode.IgnoreAspectRatio,
                    qt.Qt.TransformationMode.SmoothTransformation)
            self.video.videoSink().setImage(image)
            self.presentation_current = True
            self._paused_preview_target = None
            if self._pause_after_open:
                self.native.set_pause(1)
                self._pause_after_open = False
                self._held_position = self._position
                self.audio.suppress(True)

    def videoSink(self):
        return self.video.videoSink()

    def setSource(self, url, *, audio_only=False, start_position=None):
        if self.retired:
            return
        if self.media is not None:
            self._restore_audio_track = self.selected_audio()
            self._restore_subtitle_track = self.native.video_get_spu()
        self.finish_audio_switch()
        self._source = url
        self.generation += 1
        self.audio.suppress(True)
        self.native.stop()
        self.native.set_media(None)
        if self.media is not None:
            self.media.release()
        self.media = None
        self._position = self._duration = 0
        self._pending_seek = None
        self._seek_issued = False
        self._seek_target = self._seek_deadline = None
        self._seek_error = self._seek_has_audio_and_video = self._completed = False
        was_audio_only = self._audio_only
        self._audio_only = audio_only
        self._end_observation = None
        self._clock_observation = None
        self.clear_video_tail()
        self._last_audio_track = None
        self._played_audio = 0
        self._paused_preview_target = None
        self._pause_after_open = False
        self._held_position = None
        self._error = self.Error.NoError
        self._tracks = ((), ())
        self._opened = False
        self.presentation_current = False
        self._displayed = 0
        self._source_size = None
        self._languages = {}
        self._audio_info = {}
        if not audio_only:
            self.videoSink().setImage(qt.QImage())
        if not url.isEmpty():
            self.media = self.instance.media_new_location(url.toString())
            for option in (':network-caching=3000', ':no-sub-autodetect-file', ':no-video-title-show'):
                self.media.add_option(option)
            if start_position is not None:
                self.media.add_option(f':start-time={start_position / 1000}')
            if audio_only:
                self.media.add_option(':no-video')
            if self._software_subtitles:
                self.media.add_option(':codec=avcodec,any')
                self.media.add_option(':avcodec-hw=none')
            if self._settings is not None:
                settings = self._settings
                for option in (f':freetype-rel-fontsize={round(16 / settings.subtitle_scale)}',
                               f':audio-language={settings.audio_language}',
                               f':sub-language={settings.subtitle_language}'):
                    self.media.add_option(option)
            for name, identity in (('audio', self._restore_audio_track), ('sub', self._restore_subtitle_track)):
                if identity is not None and identity >= 0:
                    self.media.add_option(f':{name}-track-id={identity}')
            self.native.set_media(self.media)
            for subtitle, selected in self._slaves:
                self.media.slaves_add(self.vlc.MediaSlaveType.subtitle, 4 if selected else 0, subtitle)
        self.set_state(self.PlaybackState.StoppedState)
        if self._audio_only != was_audio_only:
            self.audioOnlyChanged.emit(self._audio_only)

    def set_state(self, state):
        if state != self._state:
            self._state = state
            self.playbackStateChanged.emit(state)

    def play(self, *, preserve_pause=False):
        if self.retired:
            return
        owner = self.parent()
        if not preserve_pause and not owner.playback_permitted():
            return
        if self._completed and not preserve_pause:
            # Replay restores the original A/V input after a terminal fallback.
            self.setSource(self._source, start_position=0)
        self._pause_after_open = preserve_pause
        if self.media is not None and self.native.play() == 0:
            switch = self._audio_switch
            self.audio.suppress(preserve_pause or self._pending_seek is not None)
            if switch is not None:
                switch.deadline = None if preserve_pause else monotonic() + AUDIO_SWITCH_TIMEOUT
                self._held_position = None
            elif self._held_position is not None:
                # A starvation hold may already equal the paused native clock.
                # Seeking to that exact position needlessly invalidates frames
                # and can miss the asynchronous seek acknowledgement window.
                if (self._pending_seek is not None
                        or self.native.get_time() != self._held_position):
                    if self._audio_only or self._video_tail_audio is not None:
                        self.seek_at(self._held_position)
                    else:
                        self.setPosition(self._held_position)
                self._held_position = None
            self.set_state(self.PlaybackState.PausedState if preserve_pause else self.PlaybackState.PlayingState)

    def pause(self):
        if self.retired:
            return
        self._held_position = self.position()
        if self._audio_only and self._pending_seek is None:
            self._held_position = max(self._held_position, self.native.get_time())
        if self._audio_switch is not None:
            self._audio_switch.deadline = None
        self._pause_after_open = True
        self.audio.suppress(True)
        self.native.set_pause(1)
        self.set_state(self.PlaybackState.PausedState)

    def stop(self):
        if self.retired:
            return
        self.finish_audio_switch()
        self._seek_target = self._seek_deadline = self._pending_seek = None
        self.native.stop()
        self.set_state(self.PlaybackState.StoppedState)

    def playbackState(self):
        return self._state

    def position(self):
        if self._audio_switch is not None:
            return self._audio_switch.position
        if self._pending_seek is not None:
            return self._pending_seek
        return self._held_position if self._held_position is not None else self._position

    def duration(self):
        bounds = getattr(getattr(self.parent(), 'content', None), 'media_bounds', None)
        return (bounds.get('end_ms') if bounds else None) or self._duration

    def setPosition(self, value):
        if self.retired:
            return
        target = max(0, int(value))
        if self.in_audio_tail(target) and not self._external_route:
            self.reopen_at(target, audio_only=True)
            return
        if (self._completed or self._error != self.Error.NoError or self._audio_only
                or self.native.get_state() in (self.vlc.State.Error, self.vlc.State.Ended)):
            self.reopen_at(target)
            return
        if self._video_tail_audio is not None:
            self.native.audio_set_track(self._video_tail_audio)
            self.clear_video_tail()
        self.seek_at(target)

    def reopen_at(self, position, *, audio_only=False):
        playing = self._state == self.PlaybackState.PlayingState
        startup_seek = not audio_only and self.native.video_get_spu() >= 0
        self.setSource(self._source, audio_only=audio_only,
                       start_position=position if startup_seek else None)
        self.seek_at(position)
        if startup_seek:
            # Input startup seek preserves a cue spanning this position. An
            # immediate second set_time can flush that cue from VLC's SPU queue.
            self._seek_issued = True
            self._seek_issued_at = monotonic()
            self._seek_output = (0, 0)
        self.mediaStatusChanged.emit(self.MediaStatus.BufferedMedia)
        self.play(preserve_pause=not playing)

    def seek_at(self, target):
        self._end_observation = None
        if self._audio_switch is not None:
            self._audio_switch.position = target
            if self._audio_switch.deadline is not None:
                self._audio_switch.deadline = monotonic() + AUDIO_SWITCH_TIMEOUT
            if self._held_position is not None:
                self._held_position = target
            self.positionChanged.emit(target)
            return
        self._pending_seek = target
        self._seek_target = target
        self._seek_deadline = monotonic() + SEEK_TIMEOUT
        self._clock_observation = None
        self.presentation_current = False
        self.seek_generation += 1
        self.audio.suppress(True)
        self._seek_issued = False
        if self._held_position is not None:
            self._held_position = self._pending_seek
            self._paused_preview_target = self._pending_seek
        if self.native.get_state() in (self.vlc.State.Playing, self.vlc.State.Paused):
            self.issue_seek()
        self.positionChanged.emit(self._pending_seek)

    def hold_position(self, position):
        self._held_position = position
        self._paused_preview_target = None

    def error(self):
        return self._error

    def errorString(self):
        return SEEK_ERROR if self._seek_error else ''

    def issue_seek(self):
        self._seek_has_audio_and_video = self.native.audio_get_track() >= 0 and self.native.video_get_track() >= 0
        self._seek_issued_at = monotonic()
        self._seek_output = (self.stats.played_abuffers, self.stats.decoded_video)
        self.native.set_time(self._pending_seek)
        self._seek_issued = True

    def fail_seek(self):
        self.pause()
        self._pending_seek = self._seek_target = self._seek_deadline = None
        self._seek_error = True
        self._error = self.Error.ResourceError
        self.errorOccurred.emit()

    def follow_audio_tail(self, position):
        if (self._audio_only or self._external_route
                or (self.duration() - position <= 1500 and not self.in_audio_tail(position))
                or getattr(self.parent(), 'network_waits', ())
                or self.native.audio_get_track() < 0 or self.native.video_get_track() < 0):
            return False
        self.reopen_at(position, audio_only=True)
        return True

    def in_audio_tail(self, position):
        bounds = getattr(getattr(self.parent(), 'content', None), 'media_bounds', None)
        if not bounds or self.native.audio_get_track() < 0 or self.native.video_get_track() < 0:
            return False
        video = [track.get('end_ms') for track in bounds.get('video', ())]
        audio = [track.get('end_ms') for track in bounds.get('audio', ())]
        if not video or not audio or any(value is None for value in video + audio):
            return False
        return max(video) - 100 <= position < max(audio) and max(video) < max(audio)

    def clear_video_tail(self):
        if self._video_tail_audio is not None:
            self._video_tail_audio = None
            self.videoOnlyChanged.emit(False)

    def follow_video_tail(self, position):
        if (self._video_tail_audio is not None or self._external_route or self.duration() - position <= 1500
                or getattr(self.parent(), 'network_waits', ())
                or self.native.video_get_track() < 0):
            return False
        audio = self.native.audio_get_track()
        if audio < 0 or self.native.audio_set_track(-1) != 0:
            return False
        # VLC's clock can stay attached to the finished audio stream.
        # Re-prime the remaining video without discarding its subtitle output.
        self._video_tail_audio = audio
        self.seek_at(position)
        self.videoOnlyChanged.emit(True)
        return True

    def observe_output(self, position):
        played, decoded = self.stats.played_abuffers, self.stats.decoded_video
        if played > self._played_audio and self._state == self.PlaybackState.PlayingState:
            self.audioProgress.emit()
        self._played_audio = played
        if self._state != self.PlaybackState.PlayingState:
            self._clock_observation = None
            return False
        now = monotonic()
        observation = self._clock_observation
        if observation is None or position != observation.position:
            self._clock_observation = OutputObservation(
                position, self.stats.decoded_audio, played, decoded, self.stats.displayed_pictures, now, now)
            return False
        if decoded != observation.decoded_video:
            observation.decoded_video, observation.video_changed = decoded, now
            observation.played_audio = played
        if self.stats.decoded_audio != observation.decoded_audio:
            observation.decoded_audio, observation.audio_changed = self.stats.decoded_audio, now
            observation.displayed_video = self.stats.displayed_pictures
        if self._audio_only and played != observation.played_audio:
            observation.played_audio, observation.audio_changed = played, now
        if self._audio_only and now - max(observation.audio_changed, observation.video_changed) >= SEEK_TIMEOUT:
            # Unknown stream bounds cannot justify completion. A native tail
            # which stops producing output must leave a bounded, retryable error.
            self.fail_seek()
            return True
        target = self._seek_target if self._seek_target is not None else position
        if played > observation.played_audio and now - observation.video_changed >= 1.5:
            return self.follow_audio_tail(target)
        if self.stats.displayed_pictures > observation.displayed_video and now - observation.audio_changed >= 1.5:
            return self.follow_video_tail(target)
        return False

    def finish_declared_media(self, position):
        bounds = getattr(getattr(self.parent(), 'content', None), 'media_bounds', None)
        end = bounds.get('end_ms') if bounds else None
        if (not end or self._state != self.PlaybackState.PlayingState
                or self._pending_seek is not None or self._seek_target is not None
                or position < end - 100):
            self._end_observation = None
            return False
        # VLC's final clock tick can precede the final sample boundary. Wait for
        # the clock and delivered audio to settle, rather than a late SPU EOF.
        output = position, self.stats.played_abuffers
        now = monotonic()
        if self._end_observation is None or self._end_observation[:2] != output:
            self._end_observation = (*output, now)
            return False
        if now - self._end_observation[2] < .5:
            return False
        self.stop()
        self._completed = True
        self._position = end
        self.positionChanged.emit(end)
        self.mediaStatusChanged.emit(self.MediaStatus.EndOfMedia)
        return True

    def route_renderer(self, renderer):
        if self.retired:
            return False
        position, playing = self.position(), self._state == self.PlaybackState.PlayingState
        self.finish_audio_switch()
        self._opened = False
        self.native.stop()
        if self.native.set_renderer(renderer) != 0:
            self.native.set_renderer(None)
            self._external_route = False
            self._pending_seek = position
            self._seek_issued = False
            if playing:
                self.native.play()
            return False
        self._external_route = renderer is not None
        self._error = self.Error.NoError
        self._pending_seek = position
        self._seek_issued = False
        if playing:
            self.native.play()
        return True

    def setPlaybackRate(self, value):
        self._rate = value
        if not self.retired:
            self.native.set_rate(value)

    def audioTracks(self):
        return self.metadata(self._tracks[0], self.vlc.TrackType.audio)

    def audioTrackLabels(self):
        from features.video.tracks import audio_label
        result = []
        for index, (identity, name) in enumerate(self._tracks[0]):
            if identity < 0:
                result.append('Audio off')
                continue
            info = self._audio_info.get(identity, {})
            language = self._languages.get((self.vlc.TrackType.audio.value, identity), '')
            if language and language != 'und':
                language = qt.QLocale.languageToString(qt.QLocale(language).language())
            result.append(audio_label(sum(row[0] >= 0 for row in self._tracks[0][:index + 1]),
                title=name.decode('utf-8', 'replace') if isinstance(name, bytes) else str(name),
                language=language, **info))
        return result

    def subtitleTracks(self):
        return self.metadata(self.subtitle_rows(), self.vlc.TrackType(2))  # libvlc_track_text

    def subtitle_rows(self):
        return tuple(row for row in self._tracks[1]
            if self._embedded_subtitles is None or row[0] in self._embedded_subtitles)

    def metadata(self, rows, kind):
        result = []
        for identity, label in rows:
            metadata = QMediaMetaData()
            metadata.insert(QMediaMetaData.Key.Title, label.decode('utf-8', 'replace') if isinstance(label, bytes) else str(label))
            language = self._languages.get((kind.value, identity))
            if language:
                metadata.insert(QMediaMetaData.Key.Language, qt.QLocale(language).language())
            result.append(metadata)
        return result

    def read_metadata(self):
        if self.media is None or self.retired:
            return
        table = ctypes.POINTER(ctypes.POINTER(NativeMediaTrack))()
        fetch = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(type(table)))(
            ('libvlc_media_tracks_get', self.vlc.dll))
        count = fetch(self.media, ctypes.byref(table))
        active_video = self.native.video_get_track()
        try:
            for index in range(min(count, 4096)):
                track = table[index].contents
                if track.language:
                    self._languages[(track.type, track.id)] = track.language.decode('utf-8', 'replace')
                if track.type == self.vlc.TrackType.audio.value and track.payload:
                    audio = ctypes.cast(track.payload, ctypes.POINTER(self.vlc.AudioTrack)).contents
                    self._audio_info[track.id] = dict(
                        codec=track.codec.to_bytes(4, 'little').decode('ascii', 'replace').strip('\x00 '),
                        description=track.description.decode('utf-8', 'replace') if track.description else '',
                        channels=audio.channels, sample_rate=audio.rate)
                if track.type == 1 and track.payload and track.id == active_video:
                    info = ctypes.cast(track.payload, ctypes.POINTER(self.vlc.VideoTrack)).contents
                    width, height = info.width, info.height
                    normalized = round(width * (info.sar_num or 1) / (info.sar_den or 1))
                    if 0 < normalized <= 8192:
                        width = normalized
                    if info.orientation.value in (4, 5, 6, 7):
                        width, height = height, width
                    if 0 < width <= 8192 and 0 < height <= 8192:
                        self._source_size = qt.QSize(width, height)
        finally:
            if count:
                release = ctypes.CFUNCTYPE(None, type(table), ctypes.c_uint)(
                    ('libvlc_media_tracks_release', self.vlc.dll))
                release(table, count)

    def activeAudioTrack(self):
        identity = self.selected_audio()
        return next((index for index, row in enumerate(self._tracks[0]) if row[0] == identity), -1)

    def selected_audio(self):
        if self._audio_switch is not None:
            return self._audio_switch.track
        if self._video_tail_audio is not None:
            return self._video_tail_audio
        track = self.native.audio_get_track()
        return self._last_audio_track if track < 0 and self._last_audio_track is not None else track

    def activeSubtitleTrack(self):
        return next((index for index, row in enumerate(self.subtitle_rows()) if row[0] == self.native.video_get_spu()), -1)

    def setActiveAudioTrack(self, index):
        if self.retired or not 0 <= index < len(self._tracks[0]):
            return
        self._restore_audio_track = None
        self.switch_audio(self._tracks[0][index][0])

    def switch_audio(self, identity):
        switch = self._audio_switch
        if switch is not None and switch.track == identity:
            return
        if switch is None and self.selected_audio() == identity and self._error == self.Error.NoError:
            return
        self.clear_video_tail()
        if self._state == self.PlaybackState.StoppedState:
            self.native.audio_set_track(identity)
            return
        deadline = monotonic() + AUDIO_SWITCH_TIMEOUT if self._state == self.PlaybackState.PlayingState else None
        if switch is not None:
            switch.track, switch.deadline = identity, deadline
            return
        position = self.position()
        if self._pending_seek is None and self._held_position is None:
            position = max(position, self.native.get_time())
        self._audio_switch = AudioSwitch(identity, position, deadline)
        self._pending_seek = self._paused_preview_target = None
        self._seek_target = self._seek_deadline = None
        self.seek_generation += 1
        self.presentation_current = False
        # The native seek coordinates A/V preroll. Keep valid output audible
        # once it starts: polled statistics can lag behind by a full second.
        self.audio.suppress(self._state != self.PlaybackState.PlayingState)
        self.audioSwitchChanged.emit(True, '')

    def audio_switch_buffering(self, event):
        # LibVLC calls this on the input thread. Record the cycle without
        # calling back into the decoder from its event handler.
        seek = self._audio_seek
        if seek is not None:
            if event.u.new_cache < 100:
                seek.buffering = True
                seek.buffered = False
            elif seek.buffering:
                seek.buffered = True

    def finish_audio_switch(self, error=''):
        if self._audio_switch is not None:
            self._audio_switch = self._audio_seek = None
            self.audioSwitchChanged.emit(False, error)

    def fail_audio_switch(self):
        self._error = self.Error.ResourceError
        self.pause()
        self.finish_audio_switch(AUDIO_SWITCH_ERROR)

    def poll_audio_switch(self, state, position, played, decoded_audio=None, decoded_video=None):
        switch, seek = self._audio_switch, self._audio_seek
        if switch.deadline is not None and monotonic() >= switch.deadline:
            self.fail_audio_switch()
            return
        if state not in (self.vlc.State.Playing, self.vlc.State.Paused):
            return
        if state == self.vlc.State.Playing and self._state == self.PlaybackState.PausedState:
            self.native.set_pause(1)
        if not self.native.is_seekable():
            self.fail_audio_switch()
            return
        target = (switch.track, switch.position)
        if seek is None or (seek.buffered and (seek.track, seek.position) != target):
            if self.native.audio_get_track() != switch.track and self.native.audio_set_track(switch.track) != 0:
                self.fail_audio_switch()
                return
            # The seek flushes the prior track and restarts demux and both
            # decoders at the held position. Serialize consecutive requests
            # across the native buffering boundaries.
            self._audio_seek = AudioSeek(*target)
            self.native.set_time(switch.position)
            return
        if not seek.buffered:
            return
        if decoded_audio != seek.decoded_audio:
            seek.decoded_audio = decoded_audio
            seek.decoded_video = decoded_video
            seek.observed_audio_at = monotonic()
        audio_ready = switch.track < 0 or (self._external_route and position > switch.position)
        if not self._external_route and switch.track >= 0 and played is not None:
            # LibVLC reports 100% before the decoder releases buffered audio.
            # Only an increase after the new cycle demonstrates actual output.
            if seek.played is None:
                seek.played = played
            audio_ready = played > seek.played
        if (state != self.vlc.State.Playing or self._state != self.PlaybackState.PlayingState
                or self.native.audio_get_track() != switch.track):
            return
        if audio_ready and position >= switch.position - 200:
            self._error = self.Error.NoError
            self.finish_audio_switch()
            return
        if (decoded_audio is None or decoded_video <= seek.decoded_video
                or getattr(self.parent(), 'network_waits', ())):
            return
        if position - switch.position >= 1250:
            self._error = self.Error.NoError
            self.finish_audio_switch(VIDEO_WITHOUT_AUDIO)
        elif (position <= switch.position + 100 and not audio_ready
                and monotonic() - seek.observed_audio_at >= 1.5
                and not self._external_route and self.native.audio_set_track(-1) == 0):
            # Reenabling an exhausted language can reattach VLC's clock to it.
            # Keep the chosen language for the next seek into playable audio.
            self._video_tail_audio = switch.track
            self._error = self.Error.NoError
            self.finish_audio_switch(VIDEO_WITHOUT_AUDIO)
            self.seek_at(switch.position)

    def setActiveSubtitleTrack(self, index):
        if self.retired:
            return
        self._restore_subtitle_track = None
        rows = self.subtitle_rows()
        identity = rows[index][0] if 0 <= index < len(rows) else -1
        self._slaves = [(url, False) for url, selected in self._slaves]
        if identity >= 0 and not self._software_subtitles:
            self._software_subtitles = True
            self.reload()
            self._restore_subtitle_track = identity
        else:
            if self.native.video_get_spu() != identity:
                self.native.video_set_spu(identity)
                self.seek_at(self.position())

    def reload(self):
        self.reopen_at(self.position(), audio_only=self._audio_only)

    def configure(self, settings):
        if self.retired:
            return
        previous = self._settings
        if settings.subtitle_scale != self._font_scale and getattr(self.parent(), 'casting', False):
            raise ValueError('Stop casting before changing subtitle size.')
        self._settings = settings
        self._options = dict(subtitle_delay_ms=settings.subtitle_delay_ms,
            audio_delay_ms=settings.audio_delay_ms)
        self.apply_offsets()
        if settings.subtitle_scale != self._font_scale:
            self.replace_instance(settings.subtitle_scale)
            return
        if self.media is not None and previous is not None and any(
                getattr(settings, key) != getattr(previous, key)
                for key in ('subtitle_scale', 'audio_language', 'subtitle_language')):
            self.reload()
            if previous.audio_language != settings.audio_language:
                self._restore_audio_track = None
            if previous.subtitle_language != settings.subtitle_language:
                self._restore_subtitle_track = None

    def replace_instance(self, scale):
        """VLC text renderer preferences belong to an instance, not media options."""
        opened = self.media is not None
        position, paused = self.position(), self._state != self.PlaybackState.PlayingState
        selected = self.selected_audio(), self.native.video_get_spu()
        candidate = instance_for(self.vlc, scale)
        native = candidate.media_player_new()
        try:
            native.video_set_callbacks(*self._callbacks[:3], None)
            native.video_set_format_callbacks(self._callbacks[3], self._callbacks[4])
        except BaseException:
            native.release()
            candidate.release()
            raise
        backend = self.parent().backend
        if backend.receivers is not None:
            backend.receivers.close()
            backend.receivers = None
        menu = getattr(self.parent(), 'receiver_menu', None)
        if menu is not None:
            menu.close()
            menu.clear()
        self.generation += 1
        self.audio.suppress(True)
        self.native.stop()
        self._events.event_detach(self.vlc.EventType.MediaPlayerBuffering)
        self.native.set_media(None)
        if self.media is not None:
            self.media.release()
            self.media = None
        self.native.release()
        self.instance.release()
        self.native, self.instance = native, candidate
        self._events = native.event_manager()
        self._events.event_attach(self.vlc.EventType.MediaPlayerBuffering, self.audio_switch_buffering)
        self.audio.player = native
        self.audio.setVolume(self.audio.volume())
        self._font_scale = scale
        if opened:
            self.setSource(self._source)
            self._restore_audio_track, self._restore_subtitle_track = selected
            self.setPosition(position)
            self.play(preserve_pause=paused)

    def apply_offsets(self):
        self.native.video_set_spu_delay(self._options.get('subtitle_delay_ms', 0) * 1000)
        self.native.audio_set_delay(self._options.get('audio_delay_ms', 0) * 1000)

    def add_subtitle(self, url, select=True):
        if self.retired or self.media is None:
            return False
        if self._embedded_subtitles is None:
            self._embedded_subtitles = {row[0] for row in (self.native.video_get_spu_description() or ()) if row[0] != -1}
        self._slaves = [(path, selected and not select) for path, selected in self._slaves if path != url]
        self._slaves.append((url, select))
        if select:
            # VLC 3 cannot blend SPU pictures onto opaque hardware surfaces
            # (e.g. VideoToolbox CVPN). Keep hardware decoding for movies that
            # do not use captions; reopen with software composition when needed.
            self._software_subtitles = True
            self.reload()
            self._restore_subtitle_track = None  # Explicit attachment overrides Off.
        return True

    def chapters(self):
        if self.retired:
            return []
        from features.video.chapters import Chapter
        table = ctypes.POINTER(ctypes.POINTER(self.vlc.ChapterDescription))()
        # The pinned Python binding declares the C output pointer one level too
        # shallow; use the documented ABI locally, without changing global bindings.
        fetch = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
            ctypes.POINTER(type(table)))(('libvlc_media_player_get_full_chapter_descriptions', self.vlc.dll))
        count = fetch(self.native, -1, ctypes.byref(table))
        try:
            return [Chapter(table[index].contents.time_offset,
                (table[index].contents.name or f'Chapter {index + 1}'.encode()).decode('utf-8', 'replace').strip())
                for index in range(max(0, min(count, 10000)))]
        finally:
            if count > 0:
                self.vlc.libvlc_chapter_descriptions_release(table, count)

    def poll(self):
        if self.retired or self.media is None or self._seek_error:
            return
        state = self.native.get_state()
        if state in (self.vlc.State.Playing, self.vlc.State.Paused):
            self._opened = True
            track = self.native.audio_get_track()
            if track >= 0:
                self._last_audio_track = track
        if state == self.vlc.State.Stopped and self._opened and self._state != self.PlaybackState.StoppedState:
            self.finish_audio_switch()
            self._error = self.Error.ResourceError
            self.set_state(self.PlaybackState.StoppedState)
            self.errorOccurred.emit()
            return
        if state == self.vlc.State.Playing and self.native.get_rate() != self._rate:
            self.native.set_rate(self._rate)
        if state == self.vlc.State.Error:
            self.finish_audio_switch()
            if self._error == self.Error.NoError:
                self._error = self.Error.NetworkError if self._external_route else self.Error.FormatError
                self.set_state(self.PlaybackState.StoppedState)
                self.errorOccurred.emit()
            return
        if state == self.vlc.State.Ended:
            if self._audio_switch is not None:
                if self.duration() - max(self._audio_switch.position, self.native.get_time()) > 1500:
                    self.fail_audio_switch()
                    return
                self.finish_audio_switch()
            if (self._seek_target is not None and self.duration() - self._seek_target > 1500
                    and self._seek_has_audio_and_video and not self._audio_only and not self._external_route):
                if (self.native.get_time() < self._seek_target - 500
                        or (self.media.get_stats(self.stats) and self.stats.played_abuffers > 0)):
                    self.reopen_at(self._seek_target, audio_only=True)
                    return
            if self._seek_target is not None and self.duration() - self._seek_target > 1500:
                self.fail_seek()
                return
            if self._state != self.PlaybackState.StoppedState and self._error == self.Error.NoError:
                self.set_state(self.PlaybackState.StoppedState)
                self._completed = True
                self.mediaStatusChanged.emit(self.MediaStatus.EndOfMedia)
            return
        duration = max(0, self.native.get_length())
        if duration > 0 and duration != self._duration:
            self._duration = duration
            self.durationChanged.emit(duration)
        position = max(0, self.native.get_time())
        got_stats = self.media.get_stats(self.stats)
        if self._audio_switch is not None:
            if got_stats:
                self.poll_audio_switch(state, position, self.stats.played_abuffers,
                                       self.stats.decoded_audio, self.stats.decoded_video)
            else:
                self.poll_audio_switch(state, position, None)
            if self._audio_switch is not None or self._error != self.Error.NoError:
                return
        if self._pending_seek is not None and state in (self.vlc.State.Playing, self.vlc.State.Paused):
            if not self._seek_issued:
                self.issue_seek()
            elif -200 <= position - self._pending_seek <= max(500, 500 * self._rate):
                self._pending_seek = None
        if self._seek_target is not None and self._pending_seek is None:
            advanced = position > self._seek_target + 100 and monotonic() - self._seek_issued_at >= .25
            has_output = self._external_route or (got_stats and (
                self.stats.played_abuffers > self._seek_output[0] or self.stats.decoded_video > self._seek_output[1]))
            if (advanced and has_output) or (state == self.vlc.State.Paused
                                            and abs(position - self._seek_target) <= 200):
                self._seek_target = self._seek_deadline = None
            elif position < self._seek_target - 200:
                # The reported time can jump back to the last video packet
                # after VLC initially echoes the requested time.
                self._pending_seek = self._seek_target
        if got_stats and self.observe_output(position):
            return
        if got_stats and self.finish_declared_media(position):
            return
        if self._seek_deadline is not None and monotonic() >= self._seek_deadline:
            self.fail_seek()
            return
        if self._pending_seek is None and self._state == self.PlaybackState.PlayingState and not self._pause_after_open:
            self.audio.suppress(False)
        if self._pending_seek is None and self._held_position is None and position != self._position:
            self._position = position
            self.positionChanged.emit(position)
        if state == self.vlc.State.Playing and self._pause_after_open and self._pending_seek is None:
            if self._audio_only:
                self.native.set_pause(1)
                self._pause_after_open = False
                self._held_position = position
            else:
                self._paused_preview_target = position
        if got_stats:
            displayed = self.stats.displayed_pictures
            if displayed != self._displayed:
                self._displayed = displayed
                if self.presentation_current:
                    self.renderedProgress.emit()
        tracks = tuple(tuple(row for row in (fetch() or ()) if row[0] != -1)
            for fetch in (self.native.audio_get_track_description, self.native.video_get_spu_description))
        if self.native.video_get_spu() >= 0 and not self._software_subtitles:
            self._software_subtitles = True
            self.reload()
            return
        if tracks != self._tracks:
            self._tracks = tracks
            self.read_metadata()
            if self._restore_audio_track in {row[0] for row in tracks[0]}:
                selected = self._restore_audio_track
                self._restore_audio_track = None
                if self._pause_after_open and self._state == self.PlaybackState.PausedState:
                    self.native.audio_set_track(selected)
                else:
                    self.switch_audio(selected)
            if self._restore_subtitle_track == -1 or self._restore_subtitle_track in {row[0] for row in tracks[1]}:
                if self.native.video_get_spu() != self._restore_subtitle_track:
                    self.native.video_set_spu(self._restore_subtitle_track)
                self._restore_subtitle_track = None
            self.tracksChanged.emit()
            self.apply_offsets()
            self.audio.setVolume(self.audio.volume())
            self.audio.setMuted(self.audio.isMuted())

    def retire(self):
        if self.retired:
            return
        self.retired = True
        self.finish_audio_switch()
        self.timer.stop()
        self.generation += 1
        self.audio.suppress(True)
        self.native.stop()
        self._events.event_detach(self.vlc.EventType.MediaPlayerBuffering)
        self.native.set_media(None)
        if self.media is not None:
            self.media.release()
            self.media = None
        self.videoSink().setImage(qt.QImage())
        self.audio.closed = True
        self.native.release()
        self.instance.release()
        self._slaves.clear()


class VLCPlayback:
    capabilities = PlaybackCapabilities(external_formats=('.srt', '.vtt', '.ass', '.ssa'),
        embedded_subtitle_adjustment=True, audio_delay=True, receivers=True)

    def __init__(self, owner, *, interactive=True):
        from services.video_runtime import binding
        vlc = binding(interactive=interactive)
        instance = instance_for(vlc)
        from .surface import VideoSurface
        self.video = VideoSurface()
        self.player = VLCPlayer(vlc, instance, self.video, owner)
        self.audio = self.player.audio
        self.audio.setVolume(.8)
        self.receivers = None

    def show_receivers(self, owner, anchor):
        if self.receivers is None:
            from .receivers import VLCReceivers
            self.receivers = VLCReceivers(self.player)
        owner.show_settings('cast')

    def retire(self):
        if not self.player.retired:
            self.player.audio.suppress(True)
            self.player.native.stop()
        try:
            if self.receivers is not None:
                self.receivers.close()
        finally:
            self.player.retire()
