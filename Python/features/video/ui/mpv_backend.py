"""Colour-preserving libmpv playback through the existing desktop player contract."""
from commonUtils.ui import pyside as qt
from PySide6.QtMultimedia import QMediaPlayer, QMediaMetaData
from .backend import PlaybackCapabilities
from .mpv_binding import API, Core
from .mpv_surface import ColourSurface


class ColourAudio(qt.QObject):
    mutedChanged = qt.Signal(bool)

    def __init__(self, core, parent):
        super().__init__(parent)
        self.core, self.level, self.muted, self.suppressed = core, .8, False, True

    def setVolume(self, value):
        self.level = max(0., min(1., value))
        self.core.submit('set', 'volume', self.level * 100)

    def volume(self):
        return self.level

    def setMuted(self, value):
        self.muted = bool(value)
        self.suppress(self.suppressed)
        self.mutedChanged.emit(self.muted)

    def isMuted(self):
        return self.muted

    def suppress(self, value):
        self.suppressed = bool(value)
        self.core.submit('set', 'mute', 'yes' if self.muted or self.suppressed else 'no')


class ColourPlayer(qt.QObject):
    positionChanged = qt.Signal(int)
    durationChanged = qt.Signal(int)
    tracksChanged = qt.Signal()
    mediaStatusChanged = qt.Signal(object)
    playbackStateChanged = qt.Signal(object)
    errorOccurred = qt.Signal()
    renderedProgress = qt.Signal()
    PlaybackState, Error, MediaStatus = QMediaPlayer.PlaybackState, QMediaPlayer.Error, QMediaPlayer.MediaStatus

    def __init__(self, core, video, parent):
        super().__init__(parent)
        self.core, self.video = core, video
        self.audio = ColourAudio(core, parent)
        self._source, self._position, self._duration = qt.QUrl(), 0, 0
        self._pending_seek, self._ready, self._loaded = None, False, False
        self._state, self._error = self.PlaybackState.StoppedState, self.Error.NoError
        self.generation, self.retired, self.presented, self._ended = 0, False, False, False
        self._tracks, self._chapters, self._settings, self._subtitles = [], [], None, set()
        self.source_colour, self.output_colour = {}, {}
        self.video.ready.connect(self.ready)
        self.video.failed.connect(self.failed)
        self.video.submitted.connect(self.frame_submitted)
        self.core.snapshot.connect(self.snapshot)
        self.colour_timer = qt.QTimer(self)
        self.colour_timer.setInterval(1000)
        self.colour_timer.timeout.connect(self.update_output)
        self.colour_timer.start()

    def videoSink(self):
        return self.video.videoSink()

    def ready(self):
        self._ready = True
        if not self._source.isEmpty():
            self.load_source()

    def load_source(self):
        self.core.submit('source', self.generation, self._source.toString())
        if self._pending_seek is not None:
            self.core.submit('seek', self._pending_seek)
        self.core.submit('pause', self._state != self.PlaybackState.PlayingState)

    def setSource(self, url):
        if self.retired:
            return
        self.generation += 1
        self._source, self._position, self._duration = qt.QUrl(url), 0, 0
        self._pending_seek, self._loaded, self._ended = None, False, False
        self._tracks, self._chapters, self._subtitles = [], [], set()
        self._error = self.Error.NoError
        self.audio.suppress(True)
        self.video.clear()
        self.set_state(self.PlaybackState.StoppedState)
        if self._ready:
            self.load_source()

    def source(self):
        return self._source

    def play(self):
        if not self.retired and self.parent().playback_permitted():
            if self._ended:
                self.setPosition(0)
            self.core.submit('pause', False)
            self.set_state(self.PlaybackState.PlayingState)
            self.audio.suppress(not self._loaded)

    def pause(self):
        if not self.retired:
            self.core.submit('pause', True)
            self.audio.suppress(True)
            self.set_state(self.PlaybackState.PausedState)

    def stop(self):
        if not self.retired:
            self.core.submit('command', 'stop')
            self.video.clear()
            self.set_state(self.PlaybackState.StoppedState)

    def set_state(self, state):
        if state != self._state:
            self._state = state
            self.playbackStateChanged.emit(state)

    def playbackState(self):
        return self._state

    def position(self):
        return self._position if self._pending_seek is None else self._pending_seek

    def duration(self):
        return self._duration

    def setPosition(self, value):
        if not self.retired:
            if self._ended:
                self._ended = False
                self.mediaStatusChanged.emit(self.MediaStatus.BufferedMedia)
            self._pending_seek = max(0, int(value))
            self.core.submit('seek', self._pending_seek)
            self.positionChanged.emit(self._pending_seek)

    def hold_position(self, value):
        self.setPosition(value)

    def setPlaybackRate(self, value):
        self.core.submit('set', 'speed', value)

    def error(self):
        return self._error

    def errorString(self):
        return 'The colour video renderer could not read or present this video.'

    def failed(self, message):
        if not self.retired and self._error == self.Error.NoError:
            self._error = self.Error.FormatError
            self.pause()
            self.errorOccurred.emit()

    def frame_submitted(self):
        if not self.retired and self._loaded:
            self.presented = True
            self.renderedProgress.emit()

    def snapshot(self, state):
        if self.retired or state['generation'] != self.generation or self._source.isEmpty():
            return
        self._loaded = state['loaded']
        output = state.get('video-out-params') or {}
        self.source_colour = state.get('video-params') or {}
        self.output_colour = {key: state.get(key) for key in ('target-peak', 'target-trc')}
        was_ready = self.video.source_ready
        self.video.source_ready = self._loaded and bool(output)
        width, height = output.get('dw', output.get('w', 0)), output.get('dh', output.get('h', 0))
        if width and height:
            self.videoSink().set_size(qt.QSize(int(width), int(height)))
        duration = round((state.get('duration') or 0) * 1000)
        if duration > 0 and duration != self._duration:
            self._duration = duration
            self.durationChanged.emit(duration)
        position = round((state.get('time-pos') or 0) * 1000)
        if self._pending_seek is not None and abs(position - self._pending_seek) <= 200 and not state.get('seeking'):
            self._pending_seek = None
        if self._pending_seek is None and position != self._position:
            self._position = position
            self.positionChanged.emit(position)
        tracks = state.get('track-list') or []
        if tracks != self._tracks:
            self._tracks = tracks
            self.tracksChanged.emit()
        self._chapters = state.get('chapter-list') or []
        self.audio.suppress(not self._loaded or self._state != self.PlaybackState.PlayingState)
        if self.video.source_ready != was_ready:
            self.video.update()
        if state.get('eof-reached') and not self._ended:
            self._ended = True
            self.set_state(self.PlaybackState.StoppedState)
            self.mediaStatusChanged.emit(self.MediaStatus.EndOfMedia)
        if state.get('error'):
            self.failed('Decoder error')

    def track_rows(self, kind):
        return [row for row in self._tracks if row.get('type') == kind and not row.get('external')]

    def metadata(self, kind):
        result = []
        for index, row in enumerate(self.track_rows(kind)):
            value = QMediaMetaData()
            value.insert(QMediaMetaData.Key.Title, row.get('title') or row.get('lang') or f'Track {index + 1}')
            if row.get('lang'):
                value.insert(QMediaMetaData.Key.Language, qt.QLocale(row['lang']).language())
            result.append(value)
        return result

    def audioTracks(self):
        return self.metadata('audio')

    def subtitleTracks(self):
        return self.metadata('sub')

    def activeAudioTrack(self):
        return next((i for i, row in enumerate(self.track_rows('audio')) if row.get('selected')), -1)

    def activeSubtitleTrack(self):
        return next((i for i, row in enumerate(self.track_rows('sub')) if row.get('selected')), -1)

    def select_track(self, kind, index):
        rows = self.track_rows(kind)
        identity = rows[index]['id'] if 0 <= index < len(rows) else 'no'
        self.core.submit('set', 'aid' if kind == 'audio' else 'sid', identity)

    def setActiveAudioTrack(self, index):
        self.select_track('audio', index)

    def setActiveSubtitleTrack(self, index):
        self.select_track('sub', index)

    def add_subtitle(self, url, select=True):
        if self.retired:
            return False
        if url not in self._subtitles:
            self._subtitles.add(url)
            self.core.submit('command', 'sub-add', url, 'select' if select else 'auto')
        else:
            external = next((row for row in self._tracks if row.get('external-filename') == url), None)
            if external and select:
                self.core.submit('set', 'sid', external['id'])
        return True

    def chapters(self):
        from features.video.chapters import Chapter
        return [Chapter(round(row.get('time', 0) * 1000), row.get('title') or f'Chapter {i + 1}')
                for i, row in enumerate(self._chapters)]

    def configure(self, settings):
        self._settings = settings
        for key, value in (('sub-scale', settings.subtitle_scale), ('sub-delay', settings.subtitle_delay_ms / 1000),
                           ('audio-delay', settings.audio_delay_ms / 1000), ('alang', settings.audio_language),
                           ('slang', settings.subtitle_language)):
            self.core.submit('set', key, value)
        self.update_output()

    def update_output(self):
        if self._settings is not None and not self.retired:
            self.video.configure_output(self._settings.colour_output, self._settings.tone_mapping)

    def retire(self):
        if self.retired:
            return
        self.retired = True
        self.colour_timer.stop()
        self.video.retire()  # Release GPU resources before terminating the decoder worker.
        self.core.retire()


class MPVPlayback:
    capabilities = PlaybackCapabilities(external_formats=('.srt', '.vtt', '.ass', '.ssa'),
        embedded_subtitle_adjustment=True, audio_delay=True, receivers=True)
    colour_managed = True

    def __init__(self, owner, *, interactive=True, library_path=None):
        if qt.QApplication.platformName() != 'cocoa':
            raise RuntimeError('Native colour output currently requires macOS.')
        from services.mpv_runtime import library
        api = API(library(library_path, interactive=interactive))
        from pathlib import Path
        options = dict(vo='libmpv', config='no', **{'load-scripts': 'no', 'terminal': 'no', 'osd-level': 0,
            'input-default-bindings': 'no', 'input-vo-keyboard': 'no', 'hwdec': 'auto-copy',
            'glsl-shaders': str(Path(__file__).with_name('extended_srgb.glsl')), 'gpu-shader-cache': 'no', 'icc-cache': 'no', 'sub-auto': 'no', 'ytdl': 'no',
            'keep-open': 'yes', 'cache': 'yes', 'demuxer-max-bytes': 134217728,
            'target-trc': 'pq', 'target-prim': 'bt.709', 'target-peak': 203, 'tone-mapping': 'bt.2390'})
        self.core = Core(api, options, owner)
        try:
            self.video = ColourSurface(self.core)
            self.player = ColourPlayer(self.core, self.video, owner)
            self.audio = self.player.audio
            self.audio.setVolume(.8)
        except BaseException:
            self.core.retire()
            raise

    def show_receivers(self, owner, anchor):
        owner.reopen_renderer('compatibility', cast=True)

    def retire(self):
        self.player.retire()
