"""Desktop video document; private media stays in revocable provider streams."""
from pathlib import Path
from threading import Event, Thread
from time import monotonic

from commonUtils.ui import pyside as qt
from PySide6.QtMultimedia import QMediaPlayer, QMediaMetaData

from features.video.playback import VideoContent, VIDEO_EXTENSIONS, SubtitleContent
from services.documents.video_progress import VideoProgress
from features.video.transport import VideoTransport


def clock(milliseconds):
    seconds = max(0, milliseconds // 1000)
    return f'{seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}'


from .controls import PlaybackTools
from .backend import QtPlayback
from .presentation import PlaybackPresentation
from .chrome import DockedChrome
from .panels import PlaybackPanels
from .icons import video_icon


class VideoWindow(PlaybackPresentation, PlaybackTools, DockedChrome, PlaybackPanels, qt.QMainWindow):
    idle = qt.Signal()
    queue_result = qt.Signal(object)
    chapter_result = qt.Signal(object)
    stream_problem = qt.Signal(str)
    network_wait = qt.Signal(object, bool)
    sidecar_result = qt.Signal(object)

    def __init__(self, choice, *, backend_factory=QtPlayback):
        super().__init__()
        self.choice = choice
        self.document_read_only = True
        self.closing = True  # Failed construction must also tolerate a Qt close event.
        self.retired = False
        self._retiring = False
        self.initialized = False
        self.subtitles = None
        self.external = False
        self.external_selection = None
        self.ended = False
        self.chapter_cancelled, self.chapter_worker = Event(), None
        self.chapter_data, self.chapter_menu = None, None
        self.transport_failure = None
        self.resource_changed = False
        self.resume_guard = None
        self.sidecar_worker = None
        self.sidecar_data = []
        self.deferred_sidecars = None
        self.subtitle_resources = []
        self.casting = False
        self.receiver_menu = None
        self.process_checks = ()
        from services.desktop_video_access import session_contexts
        self.process_contexts = session_contexts()
        self.backend_factory = backend_factory
        try:
            self.content = VideoContent(choice.provider, choice.path)
            self.transport = VideoTransport(self.content, failed=self.stream_problem.emit,
                waiting=self.network_wait.emit)
            from commonUtils.filesystem.storage import cache_directory
            self.progress = VideoProgress(self.content, cache_directory(create=False) / 'Video')
            self.resume_at = self.progress.load() or None
            self.build()
            self.queue_result.connect(self.queue_loaded)
            self.build_tools(cache_directory(create=False) / 'Video')
            self.build_presentation()
            self.sidecar_result.connect(self.sidecars_loaded)
            self.start_sidecars()
            state = getattr(self.progress, 'credential_state', None)
            if state is not None and state.locked_state:
                self.status.setText('Saved position needs the previous ZIP password. Use Settings → Reader history → Migrate.')
            elif self.progress.resume_notice:
                self.status.setText(self.progress.resume_notice)
            self.closing = False
            self.initialized = True
            if getattr(self, '_renderer_warning', None):
                self.status.setText(self._renderer_warning)
        except BaseException:
            self.chapter_cancelled.set()
            if self.sidecar_worker is not None:
                self.sidecar_worker.join()
            if hasattr(self, 'lifecycle'):
                self.lifecycle.close()
            if hasattr(self, 'backend'):
                self.backend.retire()
            if hasattr(self, 'transport'):
                self.transport.close()
            for resource in self.subtitle_resources:
                resource.close()
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
        if self.resume_at:
            self.player.setPosition(self.resume_at)
        self.resume_guard = None
        if self.content.restricted or self.process_contexts:
            try:
                from .privacy import VideoResumeGuard
                from services.desktop_video_access import process_authorization
                authorization, self.process_checks = process_authorization() if not self.content.restricted else (None, ())
                self.resume_guard = VideoResumeGuard(self, authorization=authorization)
            except BaseException:
                self.retire_private_content()
                self.deleteLater()
                raise
        self.startup_pending = True
        qt.QTimer.singleShot(0, self.start_initial_playback)

    def start_initial_playback(self):
        if not self.closing and self.startup_pending:
            self.toggle_play()

    def build(self):
        self.build_chrome()
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.tracksChanged.connect(self.refresh_tracks)
        self.player.mediaStatusChanged.connect(self.media_status)
        self.player.playbackStateChanged.connect(self.update_play)
        self.stream_problem.connect(self.transport_problem)
        self.player.errorOccurred.connect(self.playback_error)
        self.timer = qt.QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.checkpoint)
        self.timer.start()
        for key, action in [('Space', self.toggle_play), ('F', self.toggle_fullscreen),
                            ('Escape', self.escape_playback),
                            ('Left', lambda: self.skip(-10000)),
                            ('Right', lambda: self.skip(10000)), ('M', self.mute.click)]:
            shortcut = qt.QShortcut(qt.QKeySequence(key), self)
            shortcut.activated.connect(action)

    def update_play(self, state):
        if hasattr(self, 'requested_play') and not self.network_hold:
            if state == QMediaPlayer.PlaybackState.PausedState:
                self.requested_play = False
            elif state == QMediaPlayer.PlaybackState.PlayingState:
                self.requested_play = True
        playing = getattr(self, 'requested_play', False) or state == QMediaPlayer.PlaybackState.PlayingState
        label = 'Pause' if playing else 'Play'
        video_icon(self.play, 'pause' if playing else 'play')
        self.play.setText(label)
        self.play.setAccessibleName(label)
        self.play.setToolTip(label + ' (Space)')
        if self.status.text() in {'Ready. Press Play to start.', 'Playing.', 'Paused.'}:
            self.status.setText('Playing.' if playing else 'Paused.')

    def update_mute(self, muted):
        label = 'Unmute' if muted else 'Mute'
        self.mute.setText(label)
        self.mute.setChecked(muted)
        video_icon(self.mute, 'muted' if muted else 'speaker')
        self.mute.setAccessibleName(label)
        self.mute.setToolTip(label + ' (M)')

    def skip(self, offset):
        if self.resume_guard is not None and self.resume_guard.blocked:
            return
        try:
            self.content.check_access()
            self.seek_to(self.player.position() + offset)
        except (OSError, ValueError, PermissionError) as error:
            self.player.pause()
            self.status.setText(str(error))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow_chrome()

    def toggle_play(self):
        self.startup_pending = False
        if self.controls_locked or (self.resume_guard is not None and self.resume_guard.blocked):
            return
        if self.resource_changed:
            self.status.setText('The video changed while it was open. Close and reopen it.')
            return
        if self.requested_play:
            self.pause_requested()
            self.checkpoint()
            return
        try:
            self.content.check_access()
            self.transport.resume()
        except (OSError, ValueError, PermissionError) as error:
            self.status.setText(str(error))
            self.player.pause()
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pause_requested()
            self.checkpoint()
        else:
            if self.player.error() != QMediaPlayer.Error.NoError or self.transport_failure:
                self.resume_at = self.player.position()
                self.player.setSource(qt.QUrl())
                self.player.setSource(qt.QUrl(self.transport.url))
                self.player.setPosition(self.resume_at)
            self.transport_failure = None
            self.requested_play = True
            self.last_frame = self.last_clock = monotonic()
            self.player.play()
            self.update_play(self.player.playbackState())
            self.show_controls()

    def duration_changed(self, duration):
        if duration <= 0:
            return
        self.progress.duration = duration
        self.seek.setEnabled(True)
        self.seek.setRange(0, min(duration, 2147483647))
        if self.resume_at is not None and duration > 0:
            self.status.setText("Resumed playback. Use Playback → Start over to restart.")
            self.have_frame = False
            self.last_frame = self.last_clock = monotonic()
            self.player.setPosition(min(self.resume_at, max(0, duration - 1000)))
            self.resume_at = None
        self.position_changed(self.player.position())

    def position_changed(self, position):
        self.last_clock = monotonic()
        if not self.seek.isSliderDown():
            self.seek.setValue(position)
        duration = self.player.duration() or self.progress.duration
        self.time.setText(f'{clock(position)} / {clock(duration) if duration else "Loading duration…"}')
        self.caption.setText(self.subtitles.at(position - self.settings.subtitle_delay_ms) if self.external and self.subtitles else '')
        self.caption.setVisible(bool(self.caption.text()))

    def refresh_tracks(self):
        def label(track, index):
            parts = dict.fromkeys(str(track.stringValue(key)) for key in
                (QMediaMetaData.Key.Title, QMediaMetaData.Key.Language) if track.stringValue(key))
            return ' · '.join(parts) or f'Track {index + 1}'
        self.audio_tracks.clear()
        for index, track in enumerate(self.player.audioTracks()):
            self.audio_tracks.addItem(label(track, index), index)
        self.audio_tracks.setCurrentIndex(self.player.activeAudioTrack())
        self.subtitle_tracks.clear()
        self.subtitle_tracks.addItem('Subtitles off', -1)
        for index, track in enumerate(self.player.subtitleTracks()):
            self.subtitle_tracks.addItem(label(track, index), index)
        if self.subtitles:
            self.subtitle_tracks.addItem('External subtitles', -2)
        for index, (name, subtitles) in enumerate(self.sidecar_data):
            self.subtitle_tracks.addItem(name, -3 - index)
        selected = self.external_selection if self.external_selection is not None else (
            -2 if self.external else self.player.activeSubtitleTrack())
        self.subtitle_tracks.setCurrentIndex(self.subtitle_tracks.findData(selected))

    def select_subtitle(self, index):
        if not self.controls_allowed():
            return
        selected = self.subtitle_tracks.itemData(index)
        if selected is None:
            return
        if selected <= -3:
            name = self.sidecar_data[-3 - selected][0]
            resource = next((item for item in self.subtitle_resources if Path(item.path).name == name), None)
            self.change_setting('subtitle_file', resource.path if resource is not None else name)
            if hasattr(self.player, 'add_subtitle'):
                if self.player.add_subtitle(self.sidecar_data[-3 - selected][1]):
                    self.external_selection = selected
                    self.external = False
                return
            self.subtitles = self.sidecar_data[-3 - selected][1]
            selected = -2
        if selected >= -1:
            self.change_setting('subtitle_track', selected)
        self.external_selection = None
        self.external = selected == -2
        self.player.setActiveSubtitleTrack(-1 if self.external else selected)
        self.position_changed(self.player.position())

    def load_subtitles(self):
        if not self.controls_allowed():
            return
        from services.documents.ui.editors import choose_editor_resource
        from features.video.subtitles import Subtitles, MAX_SUBTITLE
        # A private video's subtitle picker starts in the same encrypted folder.
        choice = choose_editor_resource(self, 'open', self.content.provider,
            extensions=self.backend.capabilities.external_formats, directory=self.content.path.rpartition('/')[0])
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
            same_source = choice.provider is self.content.provider or (
                choice.provider.storage_id == self.content.provider.storage_id and
                getattr(choice.provider, 'storage_namespace', '') == getattr(self.content.provider, 'storage_namespace', ''))
            self.change_setting('subtitle_file', choice.path if same_source else '')
            if hasattr(self.player, 'add_subtitle'):
                url = self.transport.add_subtitle(resource)
                if not self.player.add_subtitle(url):
                    raise ValueError('The decoder could not attach these subtitles.')
                self.subtitle_resources.append(resource)
                self.sidecar_data.append((Path(resource.path).name, url))
                self.external_selection = -3 - (len(self.sidecar_data) - 1)
                self.refresh_tracks()
                resource = None
                return
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

    def start_sidecars(self):
        def load():
            from features.video.sidecars import discover_sidecars
            from features.video.subtitles import Subtitles, MAX_SUBTITLE
            resources = []
            rows = []
            try:
                resources = discover_sidecars(self.content,
                    cancelled=self.chapter_cancelled.is_set,
                    extensions=self.backend.capabilities.external_formats,
                    preferred=self.settings.subtitle_file)
                for resource in resources:
                    if self.chapter_cancelled.is_set():
                        break
                    try:
                        if hasattr(self.player, 'add_subtitle'):
                            url = self.transport.add_subtitle(resource)
                            self.subtitle_resources.append(resource)
                            rows.append((Path(resource.path).name, url))
                            continue
                        with resource.open() as stream:
                            subtitles = Subtitles(stream.read(MAX_SUBTITLE + 1))
                        rows.append((Path(resource.path).name, subtitles))
                    except (OSError, ValueError):
                        continue
            except (OSError, ValueError):
                pass
            finally:
                for resource in resources:
                    if resource not in self.subtitle_resources:
                        resource.close()
            if not self.chapter_cancelled.is_set():
                self.sidecar_result.emit(rows)
        self.sidecar_worker = Thread(target=load, name='video-subtitle-discovery')
        self.sidecar_worker.start()

    def sidecars_loaded(self, rows):
        if self.closing or self.chapter_cancelled.is_set():
            return
        if self.resume_guard is not None and self.resume_guard.blocked:
            self.deferred_sidecars = rows
            return
        try:
            self.content.check_access()
        except (OSError, ValueError):
            return
        # Preserve manual attachments made while discovery was still running;
        # their stable indices also identify the selected external subtitle.
        for row in rows:
            if row not in self.sidecar_data:
                self.sidecar_data.append(row)
        self.refresh_tracks()
        saved = Path(self.settings.subtitle_file).name
        if saved:
            for index, (name, _) in enumerate(self.sidecar_data):
                if name == saved:
                    self.select_subtitle(self.subtitle_tracks.findData(-3 - index))
                    break

    def restore_sidecars(self):
        if self.deferred_sidecars is not None:
            rows, self.deferred_sidecars = self.deferred_sidecars, None
            self.sidecars_loaded(rows)

    def transport_problem(self, category):
        self.resource_changed = self.resource_changed or category == 'changed'
        messages = {
            'access': 'Video access expired. Unlock the source, then press Play to retry.',
            'changed': 'The video changed while it was open. Close and reopen it.',
            'read': 'Video data could not be read. Check the connection, then press Play to retry.',
            'busy': 'The video connection is busy. Press Play to retry.',
        }
        self.transport_failure = messages.get(category, messages['read'])

    def playback_error(self, *args):
        self.requested_play = False
        self.network_hold = False
        self.show_controls()
        messages = {
            QMediaPlayer.Error.FormatError: 'This video format could not be decoded.',
            QMediaPlayer.Error.AccessDeniedError: 'Video access was denied. Unlock the source and press Play to retry.',
            QMediaPlayer.Error.NetworkError: 'The video connection failed. Press Play to retry.',
        }
        self.status.setText(self.transport_failure or messages.get(self.player.error(),
            'Playback could not continue. Press Play to retry from this position.'))

    def show_chapters(self):
        if not self.controls_allowed():
            return
        if hasattr(self.player, 'chapters'):
            self.chapter_data = self.player.chapters()
        self.show_settings('chapters')
        if self.chapter_data is not None or (self.chapter_worker is not None and self.chapter_worker.is_alive()):
            return
        def load():
            from features.video.chapters import read_chapters
            try:
                rows, error = read_chapters(self.content, cancelled=self.chapter_cancelled.is_set), False
            except (OSError, ValueError, PermissionError):
                rows, error = [], True
            if not self.chapter_cancelled.is_set():
                self.chapter_result.emit((rows, error))
        self.chapter_worker = Thread(target=load, name='video-chapters')
        self.chapter_worker.start()

    def chapters_loaded(self, result):
        if self.closing or self.chapter_cancelled.is_set():
            return
        rows, error = result
        if error:
            self.status.setText('Could not read chapters. Check access and try again.')
        self.chapter_data = rows
        self.refresh_settings('chapters')

    def seek_to(self, position):
        if self.closing or (self.resume_guard is not None and self.resume_guard.blocked):
            return
        try:
            self.content.check_access()
            duration = self.player.duration() or self.progress.duration
            position = max(0, min(duration, position) if duration else position)
            self.remember_seek(position)
            self.have_frame = False
            self.last_frame = self.last_clock = monotonic()
            if self.player.duration() <= 0:
                self.resume_at = position
            self.player.setPosition(position)
        except (OSError, ValueError, PermissionError):
            self.player.pause()
            self.status.setText('Unlock the video before seeking.')

    def toggle_fullscreen(self):
        self.fullscreen.toggle()

    def reopen_renderer(self, renderer, *, cast=False):
        """Retain the same resource and playback intent while changing decoders."""
        if not self.controls_allowed():
            return
        from commonUtils.runtime.resources.selection import ResourceChoice
        from services.documents.ui.editors import retain
        from .backend import desktop_playback
        from .vlc_backend import VLCPlayback
        playing, position, fullscreen = self.requested_play, self.player.position(), self.isFullScreen()
        self.pause_requested()
        self.checkpoint()
        provider = self.content.provider
        release = provider.acquire() if hasattr(provider, 'acquire') else lambda: None
        choice = ResourceChoice(provider, self.content.path, release)
        candidate = None
        try:
            candidate = VideoWindow(choice, backend_factory=VLCPlayback if renderer == 'compatibility' else desktop_playback)
            candidate.startup_pending = False
            candidate.player.setPosition(position)
            if not playing:
                candidate.player.pause()
                if isinstance(candidate.backend, VLCPlayback):
                    candidate.player.play(preserve_pause=True)
            if fullscreen:
                self.fullscreen.leave()
            retain(candidate)
            if fullscreen and not cast:
                candidate.fullscreen.toggle()
            if playing and not (candidate.resume_guard and candidate.resume_guard.blocked):
                qt.QTimer.singleShot(0, candidate.toggle_play)
            if cast:
                qt.QTimer.singleShot(0, candidate.show_receivers)
            self.close()
        except (OSError, RuntimeError, ValueError) as error:
            if candidate is not None:
                candidate.close()
            else:
                choice.close()
            self.status.setText(str(error))

    def show_receivers(self):
        if self.closing or (self.resume_guard is not None and self.resume_guard.blocked):
            return
        try:
            from services.desktop_video_access import require_external
            require_external(self.content)
            self.backend.show_receivers(self, self.cast_button)
        except (OSError, ValueError):
            self.status.setText('Casting is unavailable for this protected source.')

    def show_in_folder(self):
        if self.closing or (self.resume_guard is not None and self.resume_guard.blocked):
            return
        try:
            self.content.check_access()
            from .source_folder import VideoSourceFolder
            from services.documents.ui.editors import retain
            browser = retain(VideoSourceFolder(self.content))
            browser.show()
            self.close()
        except (OSError, ValueError) as error:
            self.status.setText(str(error))

    def media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.transport_failure:
                self.playback_error()
                return
            was_requested = self.requested_play
            self.requested_play = False
            self.show_controls()
            self.ended = True
            self.checkpoint(completed=True)
            if self.settings.autoplay_next and was_requested:
                qt.QTimer.singleShot(0, lambda: self.queue_move(1))
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
            try:
                self.content.check_access()
            except (OSError, ValueError, PermissionError):
                self.player.pause()
            self.status.setText('Resume unavailable: ' + str(error))
        self.idle.emit()

    def retire_private_content(self):
        if self.retired or self._retiring:
            return
        self._retiring = True
        try:
            self._retire_content()
            self.retired = True
        finally:
            self._retiring = False

    def _retire_content(self):
        self.closing = True
        self.requested_play = False
        self.audio.setMuted(True)
        self.player.pause()
        self.transport.suspend()
        self.retire_presentation()
        if self.receiver_menu is not None:
            self.receiver_menu.close()
            self.receiver_menu.clear()
        self.chapter_cancelled.set()
        if self.sidecar_worker is not None:
            self.sidecar_worker.join()
        self.sidecar_data = []
        self.deferred_sidecars = None
        if self.chapter_menu is not None:
            self.chapter_menu.close()
            self.chapter_menu.clear()
        if self.chapter_worker is not None:
            self.chapter_worker.join()
        self.chapter_data = None
        if getattr(self, "queue_worker", None) is not None:
            self.queue_worker.join()
        self.queue = None
        if self.tools_menu is not None:
            self.tools_menu.close()
            self.tools_menu.clear()
        self.cache_timer.stop()
        if self.resume_guard is not None:
            self.resume_guard.dispose()
        self.timer.stop()
        self.backend.retire()
        self.caption.clear()
        self.subtitles = None
        self.transport.close()
        for resource in self.subtitle_resources:
            resource.close()
        self.subtitle_resources = []
        self.content.close()
        self.lifecycle.close()

    def closeEvent(self, event):
        if self.initialized and not self.retired:
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
        from .backend import desktop_playback
        return retain(VideoWindow(choice, backend_factory=desktop_playback))
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
