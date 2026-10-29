"""Desktop playback tools; provider lifetime stays with the document window."""

from dataclasses import asdict, replace
from time import monotonic

from commonUtils.ui import pyside as qt
from services.documents.video_settings import SettingsStore
from features.video.session import (
    ASPECTS,
    RATES,
    FolderQueue,
    parse_time,
)


class CachedSlider(qt.QSlider):
    ranges = ()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = qt.QPainter(self)
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
        self.settings_store = SettingsStore(root)
        self.settings = self.settings_store.load()
        self.undo_position, self.undo_deadline = None, 0
        self.body_layout = self.centralWidget().layout()
        self.queue = None
        self.tools_menu = None
        self.tools_button = qt.QPushButton("Playback…")
        self.tools_button.clicked.connect(self.show_tools)
        self.action_buttons += (self.tools_button,)
        for button in self.action_buttons:
            button.setSizePolicy(
                qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Fixed
            )
        self.action_layout.addWidget(self.tools_button, 0, len(self.action_buttons) - 1)
        self.undo_button = qt.QPushButton("Undo seek")
        self.undo_button.clicked.connect(self.undo_seek)
        self.centralWidget().layout().addWidget(self.undo_button)
        self.undo_button.hide()
        self.seek.setToolTip(
            "Green strip: approximate cached byte ranges. Variable bitrate may shift the time mapping."
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

    def refresh_cache(self):
        if self.closing:
            self.cache_timer.stop()
            return
        try:
            value = self.content.buffered_ranges()
            self.seek.ranges = value["ranges"] if not value["local"] else [(0, 1)]
            self.seek.update()
        except (OSError, ValueError):
            self.seek.ranges = ()
        if monotonic() > self.undo_deadline:
            self.undo_button.hide()

    def remember_seek(self, position):
        if abs(position - self.player.position()) >= 10000:
            self.undo_position = self.player.position()
            self.undo_deadline = monotonic() + 8
            self.undo_button.show()

    def undo_seek(self):
        if self.undo_position is not None and monotonic() <= self.undo_deadline:
            position = self.undo_position
            self.undo_position = None
            self.undo_deadline = 0
            self.seek_to(position)
            self.undo_button.hide()
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
        try:
            self.settings = self.settings_store.save(
                asdict(replace(self.settings, **{key: value}))
            )
            self.apply_settings()
        except (OSError, ValueError) as error:
            self.status.setText(str(error))

    def apply_settings(self):
        self.player.setPlaybackRate(self.settings.rate)
        if hasattr(self.player, "setPitchCompensation"):
            self.player.setPitchCompensation(True)
        self.caption.setStyleSheet(
            f"font-size: {round(22 * self.settings.subtitle_scale)}px; color: white; background: black;"
        )
        self.apply_aspect()
        self.prefer_languages()

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

    def prefer_languages(self):
        from PySide6.QtMultimedia import QMediaMetaData

        for preferred, tracks, select in (
            (
                self.settings.audio_language,
                self.player.audioTracks(),
                self.player.setActiveAudioTrack,
            ),
            (
                self.settings.subtitle_language,
                self.player.subtitleTracks(),
                self.player.setActiveSubtitleTrack,
            ),
        ):
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

    def ask_setting(self, key, label, current):
        value, accepted = qt.QInputDialog.getText(
            self, "Playback preferences", label, text=str(current)
        )
        if accepted:
            try:
                self.change_setting(
                    key, int(value) if key.endswith("_ms") else value.strip()
                )
            except ValueError as error:
                self.status.setText(str(error))

    def show_tools(self):
        if self.closing or (
            self.resume_guard is not None and self.resume_guard.blocked
        ):
            return
        try:
            self.content.check_access()
        except (OSError, ValueError):
            return
        menu = self.tools_menu = qt.QMenu(self)
        menu.addAction("Go to time… (G)", self.go_to_time)
        menu.addAction("Start over", lambda: self.seek_to(0))
        undo = menu.addAction("Undo seek (Ctrl+Z)", self.undo_seek)
        undo.setEnabled(monotonic() <= self.undo_deadline)
        rate = menu.addMenu("Speed · pitch preserved")
        for value in RATES:
            action = rate.addAction(
                f"{value:g}×",
                lambda checked=False, v=value: self.change_setting("rate", v),
            )
            action.setCheckable(True)
            action.setChecked(value == self.settings.rate)
        aspect = menu.addMenu("Picture size")
        for value in ASPECTS:
            label = "Fill (crop edges)" if value == "fill" else value.title()
            action = aspect.addAction(
                label, lambda checked=False, v=value: self.change_setting("aspect", v)
            )
            action.setCheckable(True)
            action.setChecked(value == self.settings.aspect)
        subtitles = menu.addMenu("Subtitles and languages")
        subtitles.addAction("Load SRT…", self.load_subtitles)
        for value in (0.75, 1.0, 1.25, 1.5, 2.0):
            subtitles.addAction(
                f"External subtitle size {value:g}×",
                lambda checked=False, v=value: self.change_setting("subtitle_scale", v),
            )
        for key, label in [
            ("subtitle_delay_ms", "External subtitle delay (ms; positive = later)"),
            (
                "audio_language",
                "Preferred audio language code (e.g. fr; blank = default)",
            ),
            (
                "subtitle_language",
                "Preferred subtitle language code (e.g. en; blank = default)",
            ),
        ]:
            subtitles.addAction(
                label + "…",
                lambda checked=False, k=key, text=label: self.ask_setting(
                    k, text, getattr(self.settings, k)
                ),
            )
        limitation = subtitles.addAction(
            "Embedded subtitle size/delay and audio sync: available on mobile"
        )
        limitation.setEnabled(False)
        queue_menu = menu.addMenu("Current folder")
        if self.queue is None:
            self.load_queue()
            queue_menu.addAction("Loading…").setEnabled(False)
        else:
            for row in self.queue.rows():
                action = queue_menu.addAction(
                    row["name"], lambda checked=False, p=row["path"]: self.queue_open(p)
                )
                action.setCheckable(True)
                action.setChecked(row["current"])
        queue_menu.addAction("Previous (P)", lambda: self.queue_move(-1))
        queue_menu.addAction("Next (N)", lambda: self.queue_move(1))
        auto = queue_menu.addAction(
            "Play next automatically",
            lambda: self.change_setting(
                "autoplay_next", not self.settings.autoplay_next
            ),
        )
        auto.setCheckable(True)
        auto.setChecked(self.settings.autoplay_next)
        menu.popup(
            self.tools_button.mapToGlobal(qt.QPoint(0, self.tools_button.height()))
        )

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
