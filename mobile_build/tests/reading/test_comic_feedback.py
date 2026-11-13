"""Boundary guidance is directional, transient and requires a deliberate repeat."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from mobile.comic_feedback import boundary, clear, sync, physical_swipe
from features.comics.mobile.composite import spread_geometry
from features.comics.mobile.navigation import folder_comics


class Host:
    pass


class ComicFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.app = Host()
        self.app._impl = NS()
        self.app.loop = asyncio.new_event_loop()
        self.owner = Host()
        self.owner.app = self.app
        self.owner.session = NS(id='comic')
        self.adjacent = AsyncMock()
        self.addCleanup(close_loop, self.app.loop)
        self.addCleanup(clear, self.app)

    def swipe(self, direction, *, rtl=False, available=True, owner=None):
        self.app.loop.run_until_complete(boundary(owner or self.owner, direction,
            right_to_left=rtl, available=available, adjacent=self.adjacent))
        return self.app._comic_boundary_feedback

    def test_beginning_finger_respects_manga_and_second_swipe_opens_previous(self):
        for rtl, forward, back in ((False, 'right to left', 'left to right'), (True, 'left to right', 'right to left')):
            with self.subTest(rtl=rtl):
                clear(self.app)
                self.adjacent.reset_mock()
                feedback = self.swipe(-1, rtl=rtl)
                self.assertEqual('Swipe ' + forward + ' to read', feedback.reading_text)
                self.assertEqual(feedback.movement, 1 if rtl else -1)
                self.assertIn('Swipe ' + back + ' again for previous volume', feedback.message)
                self.adjacent.assert_not_awaited()
                self.swipe(-1, rtl=rtl)
                self.adjacent.assert_awaited_once_with(-1)
                self.assertFalse(feedback.message)

    def test_end_demonstrates_reading_movement_and_offers_next_volume(self):
        feedback = self.swipe(1)
        self.assertIn('End of comic', feedback.message)
        self.assertIn('next volume', feedback.message)
        self.assertIn('Swipe right to left to read', feedback.reading_text)
        self.swipe(1)
        self.adjacent.assert_awaited_once_with(1)

    def test_reader_relayout_keeps_hint_but_navigation_clears_it(self):
        feedback = self.swipe(-1)
        sync(self.app, NS(children=[NS(_reader_session_id='comic', children=[])]))
        self.assertTrue(feedback.message)
        sync(self.app, NS(children=[]))
        self.assertFalse(feedback.message)

    def test_expiry_direction_owner_changes_and_missing_neighbors_do_not_open(self):
        feedback = self.swipe(-1)
        feedback.deadline = self.app.loop.time() - 1
        self.swipe(-1)
        self.adjacent.assert_not_awaited()
        self.swipe(1)
        self.adjacent.assert_not_awaited()
        other = Host()
        other.app = self.app
        self.swipe(1, owner=other)
        self.adjacent.assert_not_awaited()
        clear(self.app)
        self.swipe(1, available=False)
        self.swipe(1, available=False)
        self.assertEqual(feedback.volume_text, '')
        self.assertNotIn('volume', feedback.message)
        self.assertFalse(feedback.armed)
        self.adjacent.assert_not_awaited()
        clear(self.app)
        self.assertFalse(feedback.message)
        self.assertIsNone(feedback.timer)

    def test_no_gutter_in_standard_and_flat_fold_spreads(self):
        for viewport, seam in (((400, 800), None), ((1200, 800), None), ((1200, 800), .5)):
            size, rects = spread_geometry([(300, 600), (400, 600)], viewport=viewport, seam=seam)
            self.assertEqual(rects[0][0] + rects[0][2], rects[1][0])
        # A reserved physical hinge remains protected.
        _, rects = spread_geometry([(300, 600), (400, 600)], viewport=(1200, 800), seam=.5, seam_gap=24)
        self.assertEqual(rects[1][0] - rects[0][0] - rects[0][2], 24)

    def test_both_boundaries_match_the_real_gesture_mapping(self):
        from mobile.reader_controls import schedule_swipe
        for rtl in (False, True):
            for direction in (-1, 1):
                for available in (None, False, True):
                    with self.subTest(rtl=rtl, direction=direction, available=available):
                        clear(self.app)
                        feedback = self.swipe(direction, rtl=rtl, available=available)
                        movement, wording = physical_swipe(rtl, direction)
                        self.owner.active_host = True
                        self.owner.workspace = NS(sessions={'comic': object()})
                        self.owner.loop = self.app.loop
                        move = AsyncMock()
                        # ImageCanvas emits +1 for a finger moving left, -1 for right.
                        schedule_swipe(self.owner, -movement, right_to_left=rtl, busy=False, move=move)
                        self.app.loop.run_until_complete(self.owner._comic_swipe_task)
                        move.assert_awaited_once_with(direction)
                        if available:
                            self.assertIn('Swipe ' + wording + ' again', feedback.volume_text)
                        else:
                            self.assertEqual(feedback.volume_text, '')
                            self.assertNotIn('volume', feedback.message)

    def test_unresolved_first_swipe_cannot_arm_a_newly_available_neighbor(self):
        self.swipe(1, available=None)
        self.swipe(1, available=True)
        self.adjacent.assert_not_awaited()
        self.swipe(1, available=True)
        self.adjacent.assert_awaited_once_with(1)

    def test_disappeared_neighbor_error_has_no_volume_offer_or_repeat(self):
        self.adjacent.return_value = 'Next volume is no longer available.'
        self.swipe(1)
        feedback = self.swipe(1)
        self.assertEqual(feedback.reading_text, self.adjacent.return_value)
        self.assertEqual(feedback.volume_text, '')
        self.assertEqual(feedback.movement, 0)
        self.assertFalse(feedback.armed)
        self.swipe(1)
        self.adjacent.assert_awaited_once()

    def test_expiry_and_owner_cleanup_dispose_presentation_and_subscription(self):
        native = Mock()
        with patch('mobile.comic_guidance.present', return_value=native):
            feedback = self.swipe(-1)
            subscription, timer = feedback.subscription, feedback.timer
            self.assertIn(subscription.key, subscription.participants.entries)
            # Deliver the real owned timer callback without a wall-clock sleep.
            timer._callback(*timer._args)
            native.close.assert_called_once()
            self.assertNotIn(subscription.key, subscription.participants.entries)
            self.assertIsNone(feedback.native)
            self.assertIsNone(feedback.timer)
            self.assertFalse(feedback.message)

    def test_cue_frames_keep_bottom_hint_separate_in_portrait_landscape_and_panes(self):
        from mobile.comic_guidance import cue_layout, cue_contents
        for width, height in ((390, 800), (800, 240), (260, 300), (260, 120), (320, 180)):
            for movement in (-1, 1):
                card, bottom, start, end = cue_layout(width, height, True, movement)
                for x, y, w, h in (card, bottom):
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x + w, width)
                    self.assertLessEqual(y + h, height)
                self.assertLess(card[1] + card[3], bottom[1])
                self.assertEqual(end > start, movement > 0)
                reading, hand, track, _, _, _ = cue_contents(*card[2:], movement)
                for x, y, w, h in (reading, hand, track):
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x + w, card[2])
                    self.assertLessEqual(y + h, card[3])
                self.assertLessEqual(hand[1] + hand[3], track[1])
                self.assertTrue(reading[1] + reading[3] <= hand[1] or reading[0] + reading[2] <= min(start, end))

    def test_desktop_backend_does_not_create_a_native_overlay(self):
        from mobile.comic_guidance import present
        backend = type('Desktop', (), {'__module__': 'toga_cocoa.app'})
        self.app._impl = backend()
        self.assertIsNone(present(self.app, self.owner, 'Reading', '', movement=1))

    def test_volume_candidates_do_not_cross_folders(self):
        rows = [dict(path=path, name=path.rsplit('/', 1)[-1], directory=False)
                for path in ('Comics/01.cbz', 'Comics/03.ZIP', 'Other/00.cbz', 'Comics/notes.md')]
        self.assertEqual(folder_comics(rows, 'Comics/02.cbz'),
                         [('Comics/01.cbz', '01.cbz'), ('Comics/03.ZIP', '03.ZIP')])

    def test_lone_pages_ignore_spread_slots_in_both_reading_directions(self):
        for page in ((300, 600), (1200, 600)):
            expected = spread_geometry([page])
            for right in (False, True):
                for viewport in ((1200, 800), (400, 800)):
                    self.assertEqual(spread_geometry([page], viewport=viewport,
                        seam=.48, seam_gap=24, single_right=right), expected)
