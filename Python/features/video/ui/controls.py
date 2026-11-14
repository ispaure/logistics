"""Desktop playback tools; provider lifetime stays with the document window."""

from dataclasses import asdict, replace
import json
from time import monotonic

from commonUtils.ui import pyside as qt
from services.documents.video_settings import VideoSettingsStore
from features.video.session import (
    FolderQueue,
    parse_time,
)


class CachedSlider(qt.QSlider):
    ranges = ()

    def paintEvent(self, event):
        super().paintEvent(event)
        with qt.QPainter(self) as painter:
            painter.setPen(qt.Qt.PenStyle.NoPen)
            painter.setBrush(qt.QColor("#72c3ad"))
            width = max(0, self.width() - 16)
            for start, stop in self.ranges:
                painter.drawRect(
                    qt.QRectF(
                        8 + start * width, self.height() - 4, (stop - start) * width, 3
                    )
                )


class PlaybackTools:
    def build_tools(self, root):
        self.settings_store = VideoSettingsStore(self.progress, root)
        self.settings = self.settings_store.load()
        self.undo_position, self.undo_deadline = None, 0
        self.body_layout = self.chrome.layout()
        self.queue = None
        self.tools_menu = None
        self.seek.setToolTip(
            "Green strip: approximate cached byte ranges. Variable bitrate may shift the time mapping."
            if self.content.remote else "Seek to a position in the video."
        )
        self.cache_timer = qt.QTimer(self)
        self.cache_timer.setInterval(1000)
        self.cache_timer.timeout.connect(self.refresh_cache)
        self.cache_timer.start()
        for key, action in [
            ("G", self.go_to_time),
            ("N", lambda: self.queue_move(1)),
            ("P", lambda: self.queue_move(-1)),
            ("Ctrl+Z", self.undo_seek),
        ]:
            shortcut = qt.QShortcut(qt.QKeySequence(key), self)
            shortcut.activated.connect(action)
        self.apply_settings()
        self.player.videoSink().videoSizeChanged.connect(self.apply_aspect)
        self.player.tracksChanged.connect(self.prefer_languages)
        self.seek.setRange(0, min(self.progress.duration, 2147483647))
        self.seek.setEnabled(self.progress.duration > 0)
        self.seek.setValue(self.resume_at or 0)
        from .player import clock
        self.time.setText(f'{clock(self.resume_at or 0)} / {clock(self.progress.duration) if self.progress.duration else "Loading duration…"}')

    def refresh_cache(self):
        if self.closing:
            self.cache_timer.stop()
            return
        try:
            value = self.content.buffered_ranges()
            self.seek.ranges = value["ranges"] if not value["local"] else ()
            self.seek.update()
        except (OSError, ValueError):
            self.seek.ranges = ()
        if monotonic() > self.undo_deadline:
            visible = self.undo_button.isVisible()
            self.undo_button.hide()
            if visible:
                self.reflow_chrome()

    def remember_seek(self, position):
        if abs(position - self.player.position()) >= 10000:
            self.undo_position = self.player.position()
            self.undo_deadline = monotonic() + 8
            self.undo_button.show()
            self.reflow_chrome()

    def undo_seek(self):
        if self.undo_position is not None and monotonic() <= self.undo_deadline:
            position = self.undo_position
            self.undo_position = None
            self.undo_deadline = 0
            self.seek_to(position)
            self.undo_button.hide()
            self.reflow_chrome()
            self.undo_deadline = 0

    def go_to_time(self):
        if self.resume_guard is not None and self.resume_guard.blocked:
            return
        value, accepted = qt.QInputDialog.getText(
            self, "Go to time", "Seconds, MM:SS or HH:MM:SS"
        )
        if accepted:
            try:
                self.seek_to(parse_time(value))
            except ValueError as error:
                self.status.setText(str(error))

    def change_setting(self, key, value):
        if not self.controls_allowed():
            return
        try:
            updates = {key: value}
            if key in {'audio_track', 'subtitle_track'}:
                tracks = self.player.audioTracks() if key == 'audio_track' else self.player.subtitleTracks()
                updates[key + '_key'] = self.track_key(tracks[value]) if type(value) is int and 0 <= value < len(tracks) else ''
            if key == 'subtitle_track' and value is not None:
                updates['subtitle_file'] = ''
            elif key == 'subtitle_file':
                updates['subtitle_track'] = None
                updates['subtitle_track_key'] = ''
            self.settings = self.settings_store.save(asdict(replace(self.settings, **updates)), explicit=updates.keys())
            if key == 'renderer':
                self.reopen_renderer(value)
                return
            self.apply_settings()
            if self.progress.state.write_status == 'locked':
                self.status.setText(self.progress.resume_notice)
        except (OSError, ValueError) as error:
            self.status.setText(str(error))

    def apply_settings(self):
        configure = getattr(self.player, 'configure', None)
        if configure is not None:
            configure(self.settings)
        self.player.setPlaybackRate(self.settings.rate)
        if hasattr(self.player, "setPitchCompensation"):
            self.player.setPitchCompensation(True)
        self.caption.setStyleSheet(
            f"font-size: {round(22 * self.settings.subtitle_scale)}px; color: white; background: black;"
        )
        self.apply_aspect()
        self.prefer_languages()
        self.speed_button.setText(f'{self.settings.rate:g}×')
        self.speed_button.setToolTip(f'Speed · {self.settings.rate:g}× · pitch preserved')
        self.picture_button.setToolTip('Picture size · ' + self.settings.aspect.title())

    def apply_aspect(self):
        # A scroll viewport clips original-size frames without forcing them to fit.
        self.video.setMinimumSize(0, 0)
        self.video.setMaximumSize(16777215, 16777215)
        original = self.settings.aspect == "original"
        self.video_viewport.setWidgetResizable(not original)
        if original:
            size = self.player.videoSink().videoSize()
            if size.isValid():
                self.video.setFixedSize(size / self.video.devicePixelRatioF())
        self.video.setAspectRatioMode(
            qt.Qt.AspectRatioMode.KeepAspectRatioByExpanding
            if self.settings.aspect == "fill"
            else qt.Qt.AspectRatioMode.KeepAspectRatio
        )

    def track_key(self, metadata):
        from PySide6.QtMultimedia import QMediaMetaData

        values = [metadata.stringValue(key) for key in (
            QMediaMetaData.Key.Title, QMediaMetaData.Key.Language, QMediaMetaData.Key.AudioCodec,
        )]
        return json.dumps([type(self.backend).__name__, *values], ensure_ascii=False)[:1024]

    def prefer_languages(self):
        from PySide6.QtMultimedia import QMediaMetaData

        for preferred, explicit, identity, tracks, select in (
            (
                self.settings.audio_language,
                self.settings.audio_track,
                self.settings.audio_track_key,
                self.player.audioTracks(),
                self.player.setActiveAudioTrack,
            ),
            (
                self.settings.subtitle_language,
                self.settings.subtitle_track,
                self.settings.subtitle_track_key,
                self.player.subtitleTracks(),
                self.player.setActiveSubtitleTrack,
            ),
        ):
            if explicit == -1:
                select(-1)
                continue
            if identity:
                matches = [index for index, track in enumerate(tracks) if self.track_key(track) == identity]
                if len(matches) == 1:
                    select(matches[0])
                    continue
            elif type(explicit) is int and 0 <= explicit < len(tracks):
                select(explicit)
                continue
            if not preferred:
                continue
            for index, track in enumerate(tracks):
                language = track.value(QMediaMetaData.Key.Language)
                code = (
                    qt.QLocale(language).name().split("_")[0]
                    if language is not None
                    else ""
                )
                if code.casefold() == preferred.casefold():
                    select(index)
                    break

    def show_tools(self):
        self.show_settings('playback')

    def load_queue(self, then=None):
        if self.queue is not None:
            if then:
                then()
            return
        self.queue_pending = then
        if getattr(self, "queue_worker", None) is not None:
            return
        from threading import Thread

        def load():
            try:
                rows = self.content.provider.list(self.content.path.rpartition("/")[0])
                result = FolderQueue(self.content.path, rows)
            except (OSError, ValueError):
                result = None
            if not self.chapter_cancelled.is_set():
                self.queue_result.emit(result)

        self.queue_worker = Thread(target=load, name="video-folder-queue")
        self.queue_worker.start()

    def queue_loaded(self, queue):
        self.queue = queue
        self.queue_worker = None
        if queue is None:
            if self.panel_name == 'queue':
                self.status.setText('Could not list this folder. Close and reopen Current folder to retry.')
        else:
            self.refresh_settings('queue')
        pending, self.queue_pending = getattr(self, "queue_pending", None), None
        if queue is not None and pending and not self.closing:
            pending()

    def queue_move(self, offset):
        if self.closing or (
            self.resume_guard is not None and self.resume_guard.blocked
        ):
            return
        if self.queue is None:
            self.load_queue(lambda: self.queue_move(offset))
        else:
            path = self.queue.adjacent(offset)
            if path:
                self.queue_open(path)

    def queue_open(self, path):
        if (
            self.closing
            or path == self.content.path
            or (self.resume_guard is not None and self.resume_guard.blocked)
        ):
            return
        try:
            self.content.check_access()
            from commonUtils.runtime.resources.selection import ResourceChoice
            from .player import open_video_choice

            choice = ResourceChoice(self.content.provider, path)
            window = open_video_choice(choice, self)
            window.show()
            self.close()
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
