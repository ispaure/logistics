"""Desktop overlays and playback intent, independent of provider transport threads."""

from time import monotonic

from commonUtils.ui import pyside as qt
from PySide6.QtMultimedia import QMediaPlayer


class PlaybackPresentation:
    def build_presentation(self):
        self.requested_play = False
        self.network_hold = False
        self.network_waits = set()
        self.last_frame = self.last_clock = monotonic()
        self.have_frame = False
        self.controls_locked = False
        self.keyboard_focus = False
        self.frame_position = 0
        self.presented_once = False
        self.watch_timer = qt.QTimer(self)
        self.watch_timer.setInterval(250)
        self.watch_timer.timeout.connect(self.watch_playback)
        self.watch_timer.start()
        self.hide_timer = qt.QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(3000)
        self.hide_timer.timeout.connect(self.hide_controls)
        self.player.videoSink().videoFrameChanged.connect(self.frame_presented)
        if hasattr(self.player, 'renderedProgress'):
            self.player.renderedProgress.connect(self.render_progress)
        self.network_wait.connect(self.network_waiting)
        self.overlay.setMouseTracking(True)
        self.overlay.installEventFilter(self)
        self.overlay.setFocusPolicy(qt.Qt.FocusPolicy.StrongFocus)
        self.unlock_button.clicked.connect(lambda: self.lock_controls(False))
        self.seek.sliderPressed.connect(self.show_controls)
        qt.QApplication.instance().installEventFilter(self)
        from .lifecycle import DesktopLifecycle
        self.lifecycle = DesktopLifecycle(self)

    def frame_presented(self, frame):
        if self.closing:
            return
        if not frame.isValid():
            self.have_frame = False
            return
        self.have_frame = True
        if not hasattr(self.player, 'renderedProgress'):
            self.render_progress()

    def render_progress(self):
        if self.closing or not self.have_frame:
            return
        self.last_frame = monotonic()
        self.frame_position = self.player.position()
        if not self.network_hold:
            self.wait_indicator.hide()
            if self.status.text() == 'Waiting for video data…':
                self.status.setText('Playing.' if self.requested_play else 'Paused.')

    def network_waiting(self, token, active):
        if self.closing:
            return
        if active:
            self.network_waits.add(token)
        else:
            self.network_waits.discard(token)
        if self.network_hold and not self.network_waits:
            self.network_hold = False
            if self.requested_play and self.playback_permitted():
                self.last_frame = self.last_clock = monotonic()
                self.player.play()

    def playback_permitted(self):
        if self.closing or (self.resume_guard is not None and self.resume_guard.blocked):
            return False
        from services.desktop_video_access import session_contexts
        if session_contexts() != self.process_contexts or any(check() for check in self.process_checks):
            return False
        if (self.content.restricted or self.process_contexts) and (
                qt.QApplication.instance().applicationState() != qt.Qt.ApplicationState.ApplicationActive):
            return False
        try:
            self.content.check_access()
        except (OSError, ValueError):
            return False
        return self.casting or ((self.isVisible() or not self.presented_once) and not self.window().isMinimized())

    def pause_requested(self):
        self.requested_play = False
        self.network_hold = False
        self.player.pause()
        self.wait_indicator.hide()
        self.update_play(self.player.playbackState())
        self.show_controls()

    def watch_playback(self):
        if self.closing:
            return
        from services.desktop_video_access import session_contexts
        if session_contexts() != self.process_contexts or any(check() for check in self.process_checks):
            # Reopen under the new authority; never keep an old external route
            # or accept a password result belonging to a retired generation.
            self.close()
            return
        self.presented_once = self.presented_once or self.isVisible()
        self.lifecycle.keep_awake(self.requested_play and self.isVisible()
            and not self.window().isMinimized() and not self.casting)
        if self.requested_play and not self.playback_permitted():
            self.pause_requested()
            return
        now = monotonic()
        waiting = (self.requested_play and not self.casting and (
            now - (max(self.last_frame, self.last_clock) if self.have_frame else self.last_frame) >= 3
            or self.network_hold))
        self.wait_indicator.setVisible(waiting)
        if waiting:
            self.show_controls()
        if (self.requested_play and self.have_frame and self.network_waits and not self.casting
                and not self.network_hold
                and (now - max(self.last_frame, self.last_clock) >= 3
                     or now - self.last_frame >= 6)):
            self.network_hold = True
            self.player.pause()
            if hasattr(self.player, 'hold_position'):
                self.player.hold_position(self.frame_position)
            else:
                self.player.setPosition(self.frame_position)
            self.status.setText('Waiting for video data…')
            self.show_controls()

    def show_controls(self):
        if self.closing or self.controls_locked:
            return
        self.chrome.show()
        self.header.show()
        self.reflow_chrome()
        self.hide_timer.start()

    def hide_controls(self):
        # Menus and keyboard focus must remain usable while chrome is visible.
        if not self.window().isFullScreen() or self.settings_pane.isVisible():
            return
        focus = qt.QApplication.focusWidget()
        if (not self.requested_play or not self.have_frame or self.network_hold
                or qt.QAccessible.isActive()
                or self.seek.isSliderDown() or qt.QApplication.activePopupWidget()
                or qt.QApplication.activeModalWidget() or self.chrome.underMouse()
                or (self.keyboard_focus and focus is not None and self.chrome.isAncestorOf(focus))):
            self.hide_timer.start()
            return
        self.chrome.hide()
        self.header.hide()

    def lock_controls(self, locked=True):
        self.controls_locked = locked
        self.close_settings()
        self.unlock_container.setVisible(locked)
        self.chrome.setVisible(not locked)
        self.header.setVisible(not locked)
        if locked:
            self.hide_timer.stop()
            for name in ('tools_menu', 'chapter_menu', 'receiver_menu'):
                menu = getattr(self, name, None)
                if menu is not None:
                    menu.close()
            self.overlay.setFocus()
        else:
            self.show_controls()

    def escape_playback(self):
        if self.controls_locked:
            self.lock_controls(False)
        elif self.settings_pane.isVisible():
            self.close_settings()
        else:
            self.fullscreen.leave()

    def eventFilter(self, watched, event):
        if not hasattr(self, 'overlay') or self.closing:
            return False
        kind = event.type()
        own_shortcut = watched is self or getattr(watched, 'parent', lambda: None)() is self
        if kind == qt.QEvent.Type.Shortcut and own_shortcut:
            self.keyboard_focus = True
            if self.controls_locked:
                if event.key().toString() == 'Esc':
                    self.lock_controls(False)
                return True
        if isinstance(watched, qt.QWidget) and self.isAncestorOf(watched):
            if kind == qt.QEvent.Type.MouseButtonPress:
                self.keyboard_focus = False
            elif kind == qt.QEvent.Type.FocusIn and event.reason() in (
                    qt.Qt.FocusReason.TabFocusReason, qt.Qt.FocusReason.BacktabFocusReason,
                    qt.Qt.FocusReason.ShortcutFocusReason):
                self.keyboard_focus = True
        if watched is self.overlay:
            if kind == qt.QEvent.Type.MouseMove:
                self.show_controls()
            elif kind == qt.QEvent.Type.MouseButtonDblClick and not self.controls_locked:
                if event.button() != qt.Qt.MouseButton.LeftButton:
                    return False
                fraction = event.position().x() / max(1, self.overlay.width())
                if fraction < .33:
                    self.skip(-10000)
                elif fraction > .67:
                    self.skip(10000)
                else:
                    self.toggle_play()
                self.show_controls()
                return True
            elif kind == qt.QEvent.Type.MouseButtonRelease:
                self.show_controls()
        return False

    def retire_presentation(self):
        self.close_settings()
        self.requested_play = False
        self.network_hold = False
        self.watch_timer.stop()
        self.hide_timer.stop()
        self.network_waits.clear()
        self.identity.clear()
        self.wait_indicator.hide()
        qt.QApplication.instance().removeEventFilter(self)
