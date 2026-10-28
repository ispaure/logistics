"""Boundary guidance is directional, transient and requires a deliberate repeat."""
import asyncio
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock

from mobile.comic_feedback import boundary, clear, sync
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
        self.addCleanup(self.app.loop.close)
        self.addCleanup(clear, self.app)

    def swipe(self, direction, *, rtl=False, available=True, owner=None):
        self.app.loop.run_until_complete(boundary(owner or self.owner, direction,
            right_to_left=rtl, available=available, adjacent=self.adjacent))
        return self.app._comic_boundary_feedback

    def test_beginning_arrow_respects_manga_and_second_swipe_opens_previous(self):
        for rtl, forward, back in ((False, '←', '→'), (True, '→', '←')):
            with self.subTest(rtl=rtl):
                clear(self.app)
                self.adjacent.reset_mock()
                feedback = self.swipe(-1, rtl=rtl)
                self.assertIn(forward + ' Swipe to read', feedback.message)
                self.assertIn('Swipe ' + back + ' again for previous volume', feedback.message)
                self.adjacent.assert_not_awaited()
                self.swipe(-1, rtl=rtl)
                self.adjacent.assert_awaited_once_with(-1)
                self.assertFalse(feedback.message)

    def test_end_has_volume_hint_without_reading_instruction(self):
        feedback = self.swipe(1)
        self.assertIn('End of comic', feedback.message)
        self.assertIn('next volume', feedback.message)
        self.assertNotIn('Swipe to read', feedback.message)
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
        self.assertIn('No next volume', feedback.message)
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
