"""Eligibility and persistence for the experimental reader cover display."""
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from commonUtils.testing.stages import TestStage
from mobile.preferences import Preferences
from mobile.reader_cover_display import BOOK_COVER, COMIC_COVER, ReaderCoverDisplay

TEST_STAGE = TestStage.REGRESSION


class ReaderCoverTests(unittest.TestCase):
    def test_cover_switches_default_off_and_persist_independently(self):
        with TemporaryDirectory() as directory:
            prefs = Preferences(directory)
            self.assertEqual((prefs.values[BOOK_COVER], prefs.values[COMIC_COVER]), ('false', 'false'))
            prefs.save(**{BOOK_COVER: 'true'})
            prefs = Preferences(directory)
            self.assertEqual((prefs.values[BOOK_COVER], prefs.values[COMIC_COVER]), ('true', 'false'))
            with self.assertRaises(ValueError):
                prefs.save(**{COMIC_COVER: 'session'})

    def test_an_enabled_switch_cannot_override_session_only_or_inactive_state(self):
        source = SimpleNamespace(session_only=False)
        reader = SimpleNamespace(source=source)
        owner = SimpleNamespace(book_reader=reader, book_record={'kind': 'epub'},
                                session=SimpleNamespace(transient=False))
        app = SimpleNamespace(visible_reader=lambda: 'book', scene_active=True, _hinge_status=3,
                              readers=SimpleNamespace(controllers={'book': owner}),
                              preferences=SimpleNamespace(values={BOOK_COVER: 'true', COMIC_COVER: 'false'}),
                              screen_privacy=SimpleNamespace(interrupted=False, captured=False))

        def candidate(allowed=True):
            return ReaderCoverDisplay.candidate(app, lambda _: allowed)

        self.assertIs(candidate()[0], reader)
        self.assertIsNone(candidate(False))
        source.session_only = True
        self.assertIsNone(candidate())
        source.session_only = False
        owner.session.transient = True
        self.assertIsNone(candidate())
        owner.session.transient = False
        for key in ('interrupted', 'captured'):
            setattr(app.screen_privacy, key, True)
            self.assertIsNone(candidate())
            setattr(app.screen_privacy, key, False)
        app._hinge_status = 1
        self.assertIsNone(candidate())
        app._hinge_status = 3
        app.scene_active = False
        self.assertIsNone(candidate())
