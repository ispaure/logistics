"""Exhaustive mixed-aspect spread traversal without native rasterization."""
from itertools import product
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from features.pdf.mobile.canvas import PDFNavigation


class PDFSpreadTests(unittest.TestCase):
    def navigation(self, sizes):
        return PDFNavigation(SimpleNamespace(count=len(sizes), page=sizes.__getitem__))

    def show(self, navigation, index, viewport):
        indices, _ = navigation.load(index, viewport)
        navigation.commit(indices, viewport)
        return indices

    @patch('features.images.validation.image_dimensions', side_effect=lambda page: page)
    def test_all_mixed_sequences_round_trip_without_repeats_or_omissions(self, dimensions):
        portrait, wide = (300, 600), (1200, 600)
        for sizes in product((portrait, wide), repeat=7):
            for viewport in ((1200, 800), (1800, 800), (600, 1000)):
                nav = self.navigation(sizes)
                spreads, target = [], 0
                while target is not None:
                    spreads.append(self.show(nav, target, viewport))
                    target = nav.next()
                self.assertEqual([page for spread in spreads for page in spread], list(range(7)))
                backwards = [nav.indices]
                while (target := nav.previous()) is not None:
                    backwards.append(self.show(nav, target, viewport))
                    self.assertLessEqual(len(backwards), 7)
                self.assertEqual(backwards, list(reversed(spreads)), (sizes, viewport))
                # Retrace once more, including every lone portrait before a wide page.
                forwards = [nav.indices]
                while (target := nav.next()) is not None:
                    forwards.append(self.show(nav, target, viewport))
                    self.assertLessEqual(len(forwards), 7)
                self.assertEqual(forwards, spreads)

    @patch('features.images.validation.image_dimensions', side_effect=lambda page: page)
    def test_back_after_each_direct_jump_excludes_the_page_being_left(self, dimensions):
        for sizes in product(((300, 600), (1200, 600)), repeat=5):
            for index in range(1, 5):
                nav = self.navigation(sizes)
                self.show(nav, index, (1200, 800))
                while (target := nav.previous()) is not None:
                    old = nav.indices
                    current = self.show(nav, target, nav.viewport)
                    self.assertEqual(current[-1] + 1, old[0])
                    self.assertTrue(set(current).isdisjoint(old))
                    # Refresh must preserve a lone page's boundary.
                    self.assertEqual(self.show(nav, target, nav.viewport), current)

    @patch('features.images.validation.image_dimensions', side_effect=lambda page: page)
    def test_resize_discards_boundaries_from_the_previous_layout(self, dimensions):
        nav = self.navigation([(300, 600)] * 5)
        self.show(nav, 0, (1200, 800))
        self.show(nav, 2, (1200, 800))
        self.show(nav, 2, (600, 1000))
        self.assertEqual(nav.previous(), 1)
        self.assertEqual(self.show(nav, 1, nav.viewport), (1,))

    @patch('features.images.validation.image_dimensions', side_effect=lambda page: page)
    def test_jumps_repartition_existing_history_without_leaving_stale_pairs(self, dimensions):
        import random
        for sizes in product(((300, 600), (1200, 600)), repeat=5):
            nav = self.navigation(sizes)
            rng = random.Random(42)
            self.show(nav, 0, (1200, 800))
            for _ in range(100):
                action = rng.choice(('next', 'previous', 'jump', 'resize'))
                before = nav.indices
                if action == 'jump':
                    self.show(nav, rng.randrange(5), nav.viewport)
                elif action == 'resize':
                    self.show(nav, before[0], rng.choice(((1200, 800), (600, 1000))))
                else:
                    target = getattr(nav, action)()
                    if target is None:
                        continue
                    after = self.show(nav, target, nav.viewport)
                    self.assertTrue(set(before).isdisjoint(after), (sizes, action, before, after))
                    self.assertEqual(after[-1] + 1 if action == 'previous' else before[-1] + 1,
                                     before[0] if action == 'previous' else after[0])
