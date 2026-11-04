"""LibVLC decoder adapted to the desktop player's Qt event/track contract."""

import ctypes
from threading import Lock

from commonUtils.ui import pyside as qt
from PySide6.QtMultimedia import QMediaPlayer, QMediaMetaData

from .backend import PlaybackCapabilities


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
        self._font_scale = 1.0
        self._opened = False
        self.presentation_current = False
        self.stats = vlc.MediaStats()
        self._displayed = 0
        self.audio = VLCAudio(self.native, parent)
        self._callbacks = self.make_callbacks()
        self.native.video_set_callbacks(*self._callbacks[:3], None)
        self.native.video_set_format_callbacks(self._callbacks[3], self._callbacks[4])
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

    def setSource(self, url):
        if self.retired:
            return
        if self.media is not None:
            self._restore_audio_track = self.native.audio_get_track()
            self._restore_subtitle_track = self.native.video_get_spu()
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
        self._paused_preview_target = None
        self._held_position = None
        self._error = self.Error.NoError
        self._tracks = ((), ())
        self._opened = False
        self.presentation_current = False
        self._displayed = 0
        self._source_size = None
        self._languages = {}
        self.videoSink().setImage(qt.QImage())
        if not url.isEmpty():
            self.media = self.instance.media_new_location(url.toString())
            for option in (':network-caching=3000', ':no-sub-autodetect-file', ':no-video-title-show'):
                self.media.add_option(option)
            if self._software_subtitles:
                self.media.add_option(':codec=avcodec,any')
                self.media.add_option(':avcodec-hw=none')
            if self._settings is not None:
                settings = self._settings
                for option in (f':freetype-rel-fontsize={round(16 / settings.subtitle_scale)}',
                               f':audio-language={settings.audio_language}',
                               f':sub-language={settings.subtitle_language}'):
                    self.media.add_option(option)
            self.native.set_media(self.media)
            for subtitle, selected in self._slaves:
                self.media.slaves_add(self.vlc.MediaSlaveType.subtitle, 4 if selected else 0, subtitle)
        self.set_state(self.PlaybackState.StoppedState)

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
        self._pause_after_open = preserve_pause
        if self.media is not None and self.native.play() == 0:
            self.audio.suppress(preserve_pause or self._pending_seek is not None)
            if self._held_position is not None:
                self.setPosition(self._held_position)
                self._held_position = None
            self.set_state(self.PlaybackState.PausedState if preserve_pause else self.PlaybackState.PlayingState)

    def pause(self):
        if self.retired:
            return
        self._held_position = self.position()
        self._pause_after_open = True
        self.audio.suppress(True)
        self.native.set_pause(1)
        self.set_state(self.PlaybackState.PausedState)

    def stop(self):
        if self.retired:
            return
        self.native.stop()
        self.set_state(self.PlaybackState.StoppedState)

    def playbackState(self):
        return self._state

    def position(self):
        if self._pending_seek is not None:
            return self._pending_seek
        return self._held_position if self._held_position is not None else self._position

    def duration(self):
        return self._duration

    def setPosition(self, value):
        if self.retired:
            return
        self._pending_seek = max(0, int(value))
        self.presentation_current = False
        self.seek_generation += 1
        self.audio.suppress(True)
        self._seek_issued = False
        if self._held_position is not None:
            self._held_position = self._pending_seek
            self._paused_preview_target = self._pending_seek
        if self.native.get_state() in (self.vlc.State.Playing, self.vlc.State.Paused):
            self.native.set_time(self._pending_seek)
            self._seek_issued = True
        self.positionChanged.emit(self._pending_seek)

    def hold_position(self, position):
        self._held_position = position
        self._paused_preview_target = None

    def error(self):
        return self._error

    def route_renderer(self, renderer):
        if self.retired:
            return False
        position, playing = self.position(), self._state == self.PlaybackState.PlayingState
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
        return next((index for index, row in enumerate(self._tracks[0]) if row[0] == self.native.audio_get_track()), -1)

    def activeSubtitleTrack(self):
        return next((index for index, row in enumerate(self.subtitle_rows()) if row[0] == self.native.video_get_spu()), -1)

    def setActiveAudioTrack(self, index):
        if self.retired:
            return
        self._restore_audio_track = None
        if 0 <= index < len(self._tracks[0]):
            self.native.audio_set_track(self._tracks[0][index][0])

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
                self.setPosition(self.position())

    def reload(self):
        position, paused = self.position(), self._state != self.PlaybackState.PlayingState
        self.setSource(self._source)
        self.setPosition(position)
        self.play(preserve_pause=paused)

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
        selected = self.native.audio_get_track(), self.native.video_get_spu()
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
        self.native.set_media(None)
        if self.media is not None:
            self.media.release()
            self.media = None
        self.native.release()
        self.instance.release()
        self.native, self.instance = native, candidate
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
        if self.retired or self.media is None:
            return
        state = self.native.get_state()
        if state in (self.vlc.State.Playing, self.vlc.State.Paused):
            self._opened = True
        if state == self.vlc.State.Stopped and self._opened and self._state != self.PlaybackState.StoppedState:
            self._error = self.Error.ResourceError
            self.set_state(self.PlaybackState.StoppedState)
            self.errorOccurred.emit()
            return
        if state == self.vlc.State.Playing and self.native.get_rate() != self._rate:
            self.native.set_rate(self._rate)
        if state == self.vlc.State.Error:
            if self._error == self.Error.NoError:
                self._error = self.Error.NetworkError if self._external_route else self.Error.FormatError
                self.set_state(self.PlaybackState.StoppedState)
                self.errorOccurred.emit()
            return
        if state == self.vlc.State.Ended:
            if self._state != self.PlaybackState.StoppedState:
                self.set_state(self.PlaybackState.StoppedState)
                self.mediaStatusChanged.emit(self.MediaStatus.EndOfMedia)
            return
        duration = max(0, self.native.get_length())
        if duration > 0 and duration != self._duration:
            self._duration = duration
            self.durationChanged.emit(duration)
        position = max(0, self.native.get_time())
        if self._pending_seek is not None and state in (self.vlc.State.Playing, self.vlc.State.Paused):
            if self._seek_issued and abs(position - self._pending_seek) <= 200:
                self._pending_seek = None
            elif not self._seek_issued:
                self.native.set_time(self._pending_seek)
                self._seek_issued = True
        if self._pending_seek is None and self._state == self.PlaybackState.PlayingState and not self._pause_after_open:
            self.audio.suppress(False)
        if self._pending_seek is None and self._held_position is None and position != self._position:
            self._position = position
            self.positionChanged.emit(position)
        if state == self.vlc.State.Playing and self._pause_after_open and self._pending_seek is None:
            self._paused_preview_target = position
        if self.media.get_stats(self.stats):
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
                if self.native.audio_get_track() != self._restore_audio_track:
                    self.native.audio_set_track(self._restore_audio_track)
                self._restore_audio_track = None
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
        self.timer.stop()
        self.generation += 1
        self.audio.suppress(True)
        self.native.stop()
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
