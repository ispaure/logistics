"""Docked geometry and usable playback panels at small desktop window sizes."""
from pathlib import Path
from unittest.mock import patch

from commonUtils.testing.stages import TestStage, stage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice

TEST_STAGE = TestStage.REGRESSION


class DockedVideoTests(QtTestCase):
    def test_chapters_folder_and_favourites_have_distinct_glyphs(self):
        from features.video.ui.icons import video_icon
        images = []
        for name in ('chapters', 'queue', 'heart'):
            button = qt.QToolButton()
            video_icon(button, name)
            images.append(button.icon().pixmap(24, 24).toImage())
            button.deleteLater()
        self.assertNotEqual(images[0], images[1])
        self.assertNotEqual(images[1], images[2])

    def make_player(self, root, *, backend_factory=None):
        from features.video.ui.player import VideoWindow
        from features.video.ui.vlc_backend import VLCPlayback
        from tests.readers.video_fixtures import bundled_movie
        movie = bundled_movie('speed-with-audio.mkv', root)
        options = dict(backend_factory=backend_factory or (lambda owner: VLCPlayback(owner, interactive=False)))
        with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'state'):
            window = VideoWindow(ResourceChoice(LocalFiles(root), movie.name), **options)
        window.startup_pending = False
        if hasattr(window.player, 'native'):
            window.player.native.audio_output_set('adummy')
        window.audio.setMuted(True)
        if qt.QApplication.platformName() != 'offscreen':
            window.setAttribute(qt.Qt.WidgetAttribute.WA_ShowWithoutActivating)
            window.setWindowFlag(qt.Qt.WindowType.WindowDoesNotAcceptFocus)
        window.show()
        self.addCleanup(window.close)
        return window

    @staticmethod
    def bounds(widget, window):
        return qt.QRect(widget.mapTo(window, qt.QPoint()), widget.size())

    def test_all_panels_and_controls_fit_without_covering_picture(self):
        from logistics_build.build_retention import scratch
        evidence = Path(__file__).resolve().parents[3] / 'test-results/video-docked-layout'
        evidence.mkdir(parents=True, exist_ok=True)
        with scratch() as root:
            window = self.make_player(root)
            window.toggle_play()
            self.wait_until(lambda: window.have_frame and window.player.position() > 100)
            window.pause_requested()
            window.status.setText('Read failed. Check your connection and press Play to retry. ' * 8)
            window.audio_tracks.addItem('A very long audio track name ' * 10, 0)
            window.subtitle_tracks.addItem('A very long subtitle track name ' * 10, -1)
            window.caption.setText('A long subtitle that wraps within the video area.')
            window.caption.show()
            sizes = ((1000, 720), (760, 480), (560, 420), (480, 320), (360, 360), (320, 480), (320, 320))
            for width, height in sizes:
                for panel in (None, 'speed', 'picture', 'audio', 'subtitles', 'chapters', 'queue', 'playback'):
                    with self.subTest(size=(width, height), panel=panel):
                        window.close_settings()
                        window.resize(width, height)
                        if panel:
                            window.show_settings(panel)
                        qt.QApplication.processEvents()
                        # A minimum-size expansion would hide the very bug these
                        # checks protect against; require the requested dimensions.
                        self.assertEqual(window.size(), qt.QSize(width, height))
                        video = self.bounds(window.stage, window)
                        self.assertGreaterEqual(video.height(), 48)
                        controls = [*window.header_buttons, *[button for button in window.utility_buttons if button.isVisible()],
                                    window.previous_video, window.backward, window.play,
                                    window.forward, window.next_video, window.mute, window.seek, window.time]
                        if panel:
                            controls.append(window.settings_pane)
                            self.assertGreaterEqual(window.settings_scroll.viewport().height(), 24)
                            if height < 400 and width < 760:
                                self.assertTrue(window.panel_selector.isVisible())
                                self.assertEqual(window.panel_selector.count(), 7 + int(window.backend.capabilities.receivers))
                        for control in controls:
                            self.assertTrue(control.isVisible(), control.accessibleName())
                            rect = self.bounds(control, window)
                            self.assertTrue(window.rect().contains(rect), (control.accessibleName(), rect, window.rect()))
                            self.assertFalse(video.intersects(rect), (control.accessibleName(), rect, video))
                        buttons = [control for control in controls if isinstance(control, qt.QAbstractButton)]
                        for number, button in enumerate(buttons):
                            for other in buttons[number + 1:]:
                                self.assertFalse(self.bounds(button, window).intersects(self.bounds(other, window)),
                                                 (button.accessibleName(), self.bounds(button, window),
                                                  other.accessibleName(), self.bounds(other, window)))
                        if panel in (None, 'subtitles', 'playback'):
                            window.grab().save(str(evidence / f'{width}x{height}-{panel or "player"}.png'))
            window.close()

    @stage(TestStage.EXTENDED)
    def test_default_vlc_surface_renders_inside_small_docked_windows(self):
        from logistics_build.build_retention import scratch
        from features.video.ui.vlc_backend import VLCPlayback
        evidence = Path(__file__).resolve().parents[3] / 'test-results/video-docked-layout'
        evidence.mkdir(parents=True, exist_ok=True)
        with scratch() as root:
            window = self.make_player(root, backend_factory=lambda owner: VLCPlayback(owner, interactive=False))
            window.toggle_play()
            self.wait_until(lambda: window.have_frame and window.player.position() > 100, timeout=20)
            window.pause_requested()
            self.assertFalse(window.video.image.isNull())
            for width, height in ((1000, 720), (560, 420), (480, 320), (360, 360), (320, 320)):
                for panel in (None, 'audio', 'subtitles', 'playback'):
                    with self.subTest(size=(width, height), panel=panel):
                        window.close_settings()
                        window.resize(width, height)
                        if panel:
                            window.show_settings(panel)
                        qt.QApplication.processEvents()
                        self.assertEqual(window.size(), qt.QSize(width, height))
                        video = self.bounds(window.stage, window)
                        for control in (*window.header_buttons, *window.utility_buttons, window.play, window.seek):
                            if control.isVisible():
                                rect = self.bounds(control, window)
                                self.assertTrue(window.rect().contains(rect))
                                self.assertFalse(video.intersects(rect))
                        window.grab().save(str(evidence / f'vlc-{width}x{height}-{panel or "player"}.png'))
            window.close()

    def test_large_font_reflows_and_lock_does_not_move_picture(self):
        from logistics_build.build_retention import scratch
        with scratch() as root:
            window = self.make_player(root)
            font = window.font()
            font.setPointSizeF(font.pointSizeF() * 1.4)
            window.setFont(font)
            window.resize(420, 420)
            qt.QApplication.processEvents()
            self.assertEqual(window.width(), 420)
            before = self.bounds(window.stage, window)
            window.lock_controls()
            qt.QApplication.processEvents()
            self.assertEqual(self.bounds(window.stage, window), before)
            self.assertTrue(window.unlock_button.isVisible())
            window.unlock_button.click()
            qt.QApplication.processEvents()
            self.assertEqual(self.bounds(window.stage, window), before)
            self.assertTrue(window.play.isVisible())
            window.requested_play = window.have_frame = True
            window.hide_controls()
            self.assertTrue(window.chrome.isVisible())  # Windowed deck stays available.
            window.resize(320, 320)
            window.show_settings('playback')
            window.remember_seek(window.player.position() + 15000)
            window.wait_indicator.show()
            window.show_controls()
            qt.QApplication.processEvents()
            self.assertEqual(window.size(), qt.QSize(320, 320))
            self.assertTrue(window.undo_button.isVisible())
            self.assertGreaterEqual(window.settings_scroll.viewport().height(), 24)
            self.assertFalse(self.bounds(window.play, window).intersects(self.bounds(window.stage, window)))
            window.close()

    def test_regular_markdown_embeds_start_paused_at_zero_in_both_modes(self):
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import bundled_movie
        from services.documents.markdown import prepare_markdown
        from services.documents.ui.markdown import MarkdownStorage, PrivateMarkdownWindow
        from PySide6.QtMultimedia import QMediaPlayer
        with scratch() as root:
            movie = bundled_movie('speed-with-audio.mkv', root)
            path = root / 'example.md'
            path.write_text(f'# Embedded movie\n\n![Movie]({movie.name})\n')
            provider = LocalFiles(root)
            data, resources = prepare_markdown(provider, path)
            media = resources.media
            storage = MarkdownStorage(provider, path, data, resources, lambda *args: None)
            window = PrivateMarkdownWindow(path, storage, edit=False)
            window.show()
            try:
                for view, editing in ((window.viewer.browser, False), (window.viewer.formatted_editor, True)):
                    window.viewer.set_editing(editing)
                    self.wait_until(lambda: bool(view.inline_videos.cards))
                    card = next(iter(view.inline_videos.cards.values()))
                    self.assertTrue(card.player.source().isEmpty())
                    self.assertEqual(card.player.position(), 0)
                    self.assertEqual(card.player.playbackState(), QMediaPlayer.PlaybackState.StoppedState)
                    self.assertTrue(card.play.isVisible())
                    self.assertTrue(card.seek.isVisible())
            finally:
                window.retire_private_content()
                window.close()
            self.assertTrue(media.closed)

    def test_favourite_and_panel_settings_use_existing_services(self):
        from desktop.document_catalog import catalog
        from logistics_build.build_retention import scratch
        with scratch() as root, patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'state'), patch(
                'desktop.document_catalog.cache_directory', return_value=root / 'state'):
            window = self.make_player(root)
            window.favourite_button.click()
            self.assertEqual(catalog().entries()[0]['title'], window.choice.path)
            window.show_settings('speed')
            speed = window.settings_scroll.widget().findChild(qt.QComboBox)
            index = speed.findData(1.5)
            speed.setCurrentIndex(index)
            speed.activated.emit(index)
            self.assertEqual(window.settings.rate, 1.5)
            self.assertEqual(window.settings_store.load().rate, 1.5)
            self.assertEqual(window.speed_button.text(), '1.5×')
            window.show_settings('queue')
            auto = window.settings_scroll.widget().findChild(qt.QCheckBox)
            auto.click()
            self.assertTrue(window.settings.autoplay_next)
            window.close_settings()
            window.show_settings('playback')
            entry = window.settings_scroll.widget().findChild(qt.QLineEdit)
            with patch.object(window, 'seek_to') as seek:
                entry.setText('1:02.5')
                entry.returnPressed.emit()
                seek.assert_called_once_with(62500)
            window.close()

    def test_fullscreen_isolates_picture_and_restores_document_slot(self):
        from logistics_build.build_retention import scratch
        from desktop.documents import DocumentPane
        with scratch() as root:
            window = self.make_player(root)
            pane = DocumentPane(window)
            pane.resize(1000, 720)
            pane.show()
            qt.QApplication.processEvents()
            slot = pane.layout().indexOf(window)
            self.assertFalse(pane.storage_location.actions_button.isVisible())
            self.assertFalse(hasattr(window, 'identity'))
            self.assertFalse(hasattr(window, 'floating'))
            window.toggle_fullscreen()
            qt.QApplication.processEvents()
            self.assertIsNone(window.parentWidget())
            self.assertTrue(window.isFullScreen())
            self.assertEqual(self.bounds(window.stage, window), window.centralWidget().geometry())
            before = self.bounds(window.stage, window)
            window.requested_play = window.have_frame = True
            window.hide_controls()
            qt.QApplication.processEvents()
            self.assertEqual(self.bounds(window.stage, window), before)
            window.escape_playback()
            qt.QApplication.processEvents()
            self.assertIs(window.parentWidget(), pane)
            self.assertEqual(pane.layout().indexOf(window), slot)
            self.assertFalse(window.fullscreen_action.isChecked())
            window.toggle_fullscreen()
            qt.QApplication.processEvents()
            window.showNormal()  # Native window-manager exit, outside our action.
            self.wait_until(lambda: window.parentWidget() is pane)
            self.assertEqual(pane.layout().indexOf(window), slot)
            self.assertFalse(window.fullscreen_action.isChecked())
            window.close()
            pane.close()
            pane.deleteLater()
