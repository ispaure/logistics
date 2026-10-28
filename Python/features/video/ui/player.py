"""Qt/FFmpeg video document; private media stays in revocable provider streams."""
from pathlib import Path

from commonUtils.ui import pyside as qt
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaMetaData
from PySide6.QtMultimediaWidgets import QVideoWidget

from features.video.playback import VideoContent, VIDEO_EXTENSIONS, SubtitleContent
from services.documents.video_progress import VideoProgress
from features.video.transport import VideoTransport


def clock(milliseconds):
    seconds = max(0, milliseconds // 1000)
    return f'{seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}'


class VideoWindow(qt.QMainWindow):
    idle = qt.Signal()

    def __init__(self, choice):
        super().__init__()
        self.choice = choice
        self.document_read_only = True
        self.closing = True  # Failed construction must also tolerate a Qt close event.
        self.subtitles = None
        self.external = False
        self.ended = False
        try:
            self.content = VideoContent(choice.provider, choice.path)
            self.transport = VideoTransport(self.content)
            from commonUtils.filesystem.storage import cache_directory
            self.progress = VideoProgress(self.content, cache_directory(create=False) / 'Video')
            self.resume_at = self.progress.load()
            self.build()
            self.closing = False
        except BaseException:
            if hasattr(self, 'transport'):
                self.transport.close()
            if hasattr(self, 'content'):
                self.content.close()
            self.deleteLater()
            raise
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(Path(choice.path).name)
        self.resize(1000, 720)
        from services.documents.ui.private_views import protect_private_view
        protect_private_view(self, self.content.provider)
        self.destroyed.connect(choice.close)
        self.player.setSource(qt.QUrl(self.transport.url))
        self.resume_guard = None
        if self.content.restricted:
            try:
                from .privacy import VideoResumeGuard
                self.resume_guard = VideoResumeGuard(self)
            except BaseException:
                self.retire_private_content()
                self.deleteLater()
                raise

    def build(self):
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.8)
        self.player.setAudioOutput(self.audio)
        body = qt.QWidget()
        self.setCentralWidget(body)
        layout = qt.QVBoxLayout(body)
        self.video = QVideoWidget()
        self.player.setVideoOutput(self.video)
        layout.addWidget(self.video, 1)
        self.caption = qt.QLabel()
        self.caption.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.caption.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        self.caption.setStyleSheet('font-size: 22px; color: white; background: black;')
        layout.addWidget(self.caption)
        row = qt.QHBoxLayout()
        self.play = qt.QPushButton('Play')
        self.play.clicked.connect(self.toggle_play)
        row.addWidget(self.play)
        self.seek = qt.QSlider(qt.Qt.Orientation.Horizontal)
        self.seek.setAccessibleName('Video position')
        self.seek.sliderReleased.connect(lambda: self.player.setPosition(self.seek.value()))
        row.addWidget(self.seek, 1)
        self.time = qt.QLabel('0:00:00 / 0:00:00')
        row.addWidget(self.time)
        self.volume = qt.QSlider(qt.Qt.Orientation.Horizontal)
        self.volume.setAccessibleName('Volume')
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setMaximumWidth(100)
        self.volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        row.addWidget(self.volume)
        layout.addLayout(row)
        row = qt.QHBoxLayout()
        self.audio_tracks, self.subtitle_tracks = qt.QComboBox(), qt.QComboBox()
        self.audio_tracks.setAccessibleName('Audio track')
        self.subtitle_tracks.setAccessibleName('Subtitles')
        self.audio_tracks.activated.connect(lambda index: self.player.setActiveAudioTrack(self.audio_tracks.itemData(index)))
        self.subtitle_tracks.activated.connect(self.select_subtitle)
        row.addWidget(self.audio_tracks)
        row.addWidget(self.subtitle_tracks)
        attach = qt.QPushButton('Load SRT…')
        attach.clicked.connect(self.load_subtitles)
        row.addWidget(attach)
        fullscreen = qt.QPushButton('Fullscreen (F)')
        fullscreen.clicked.connect(self.toggle_fullscreen)
        row.addWidget(fullscreen)
        self.floating = qt.QPushButton('Floating window')
        self.floating.setEnabled(not self.content.restricted)
        self.floating.clicked.connect(self.toggle_floating)
        row.addWidget(self.floating)
        layout.addLayout(row)
        self.status = qt.QLabel('Cloud streaming may buffer or fail when seeking; resume is kept only while this player is open.'
                               if self.content.remote else 'Ready. Press Play to start.')
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.tracksChanged.connect(self.refresh_tracks)
        self.player.mediaStatusChanged.connect(self.media_status)
        self.player.playbackStateChanged.connect(lambda state: self.play.setText('Pause' if state == QMediaPlayer.PlaybackState.PlayingState else 'Play'))
        self.player.errorOccurred.connect(lambda *_: self.status.setText('Playback failed: ' + self.player.errorString()))
        self.timer = qt.QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.checkpoint)
        self.timer.start()
        for key, action in [('Space', self.toggle_play), ('F', self.toggle_fullscreen),
                            ('Escape', lambda: self.window().showNormal()),
                            ('Left', lambda: self.player.setPosition(max(0, self.player.position() - 10000))),
                            ('Right', lambda: self.player.setPosition(self.player.position() + 10000))]:
            shortcut = qt.QShortcut(qt.QKeySequence(key), self)
            shortcut.activated.connect(action)

    def toggle_play(self):
        if self.resume_guard is not None and self.resume_guard.blocked:
            return
        try:
            self.content.check_access()
            self.transport.resume()
        except (OSError, ValueError, PermissionError) as error:
            self.status.setText(str(error))
            self.player.pause()
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.checkpoint()
        else:
            self.player.play()

    def duration_changed(self, duration):
        self.seek.setRange(0, min(duration, 2147483647))
        if self.resume_at and duration > 0:
            self.player.setPosition(min(self.resume_at, max(0, duration - 1000)))
            self.resume_at = 0

    def position_changed(self, position):
        if not self.seek.isSliderDown():
            self.seek.setValue(position)
        self.time.setText(f'{clock(position)} / {clock(self.player.duration())}')
        self.caption.setText(self.subtitles.at(position) if self.external and self.subtitles else '')

    def refresh_tracks(self):
        def label(track, index):
            return str(track.stringValue(QMediaMetaData.Key.Title) or track.stringValue(QMediaMetaData.Key.Language) or f'Track {index + 1}')
        self.audio_tracks.clear()
        for index, track in enumerate(self.player.audioTracks()):
            self.audio_tracks.addItem(label(track, index), index)
        self.audio_tracks.setCurrentIndex(self.player.activeAudioTrack())
        self.subtitle_tracks.clear()
        self.subtitle_tracks.addItem('Subtitles off', -1)
        for index, track in enumerate(self.player.subtitleTracks()):
            self.subtitle_tracks.addItem(label(track, index), index)
        if self.subtitles:
            self.subtitle_tracks.addItem('External SRT', -2)
        selected = -2 if self.external else self.player.activeSubtitleTrack()
        self.subtitle_tracks.setCurrentIndex(self.subtitle_tracks.findData(selected))

    def select_subtitle(self, index):
        selected = self.subtitle_tracks.itemData(index)
        self.external = selected == -2
        self.player.setActiveSubtitleTrack(-1 if self.external else selected)
        self.position_changed(self.player.position())

    def load_subtitles(self):
        from services.documents.ui.editors import choose_editor_resource
        from features.video.subtitles import Subtitles, MAX_SUBTITLE
        # A private video's subtitle picker starts in the same encrypted folder.
        choice = choose_editor_resource(self, 'open', self.content.provider,
            extensions=('.srt',), directory=self.content.path.rpartition('/')[0])
        if choice is None:
            return
        resource = None
        try:
            from services.documents.storage import DocumentPolicy
            if (not DocumentPolicy.for_provider(choice.provider).persistent and
                    (choice.provider.storage_id, getattr(choice.provider, 'storage_namespace', '')) !=
                    (self.content.provider.storage_id, getattr(self.content.provider, 'storage_namespace', ''))):
                raise ValueError('Choose private subtitles from the same storage as the video.')
            resource = SubtitleContent(choice.provider, choice.path)
            with resource.open() as stream:
                self.subtitles = Subtitles(stream.read(MAX_SUBTITLE + 1))
            self.external = True
            self.player.setActiveSubtitleTrack(-1)
            self.refresh_tracks()
            self.position_changed(self.player.position())
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
        finally:
            if resource is not None:
                resource.close()
            choice.close()

    def toggle_fullscreen(self):
        window = self.window()
        window.showNormal() if window.isFullScreen() else window.showFullScreen()

    def toggle_floating(self):
        try:
            self.content.require_external()
        except (OSError, ValueError, PermissionError) as error:
            self.status.setText(str(error))
            return
        from commonUtils.ui.document_host import current_document_host
        host = current_document_host()
        record = host.records.get(self) if host is not None else None
        if record is not None and not record['detached']:
            dock = record['dock']
            if dock.workspace.detach_dock(dock) is None:
                self.status.setText('Detach this document before using floating playback.')
                return
        window = self.window()
        floating = not bool(window.windowFlags() & qt.Qt.WindowType.WindowStaysOnTopHint)
        window.setWindowFlag(qt.Qt.WindowType.WindowStaysOnTopHint, floating)
        if floating:
            window.resize(560, 420)
        window.show()

    def media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.ended = True
            self.checkpoint(completed=True)
        elif status == QMediaPlayer.MediaStatus.BufferedMedia:
            self.ended = False

    def checkpoint(self, completed=False):
        if self.closing or (self.resume_guard is not None and self.resume_guard.blocked):
            return
        if self.player.duration() <= 0:
            return
        try:
            self.content.check_access()
            self.progress.save(self.player.position(), completed=completed or self.ended)
        except (OSError, ValueError, PermissionError) as error:
            self.player.pause()
            self.status.setText('Resume position: ' + str(error))
        self.floating.setEnabled(not self.content.restricted)
        self.idle.emit()

    def retire_private_content(self):
        if self.resume_guard is not None:
            self.resume_guard.dispose()
        self.timer.stop()
        self.player.stop()
        self.player.setSource(qt.QUrl())
        self.caption.clear()
        self.subtitles = None
        self.transport.close()
        self.content.close()

    def closeEvent(self, event):
        if not self.closing:
            self.checkpoint()
            self.closing = True
            self.timer.stop()
            self.retire_private_content()
        event.accept()


def open_video_choice(choice, parent=None):
    from services.documents.ui.editors import retain
    try:
        from features.application import registry
        if not registry.is_feature_enabled('video'):
            raise ValueError('Enable Video Player in Settings → Features before opening a video.')
        return retain(VideoWindow(choice))
    except BaseException:
        choice.close()
        raise


def open_video(path, parent=None):
    from services.documents.ui.editors import local_document_choice
    return open_video_choice(local_document_choice(path), parent)


def launch(parent):
    from services.documents.ui.editors import choose_editor_resource
    choice = choose_editor_resource(parent, 'open', extensions=tuple(sorted(VIDEO_EXTENSIONS)))
    return open_video_choice(choice, parent) if choice is not None else None
