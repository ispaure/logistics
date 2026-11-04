"""Help's host-owned Browse controls track compact versus pinned layouts."""
from pathlib import Path
import unittest

from commonUtils.testing.stages import TestStage
from mobile.documentation_ui import show_documentation
from mobile_build.tests.documents import test_documentation_ui as fixtures

TEST_STAGE = TestStage.REGRESSION


class DocumentationToolbarTests(unittest.TestCase):
    setUp = fixtures.DocumentationTests.setUp
    tearDown = fixtures.DocumentationTests.tearDown

    def test_browse_controls_follow_phone_tablet_transitions(self):
        root = Path(self.temporary.name) / 'guides'
        root.mkdir()
        first = root / 'guides.md'
        first.write_text('# Help')
        self.app.show_settings()
        owner = show_documentation(self.app, root, first)
        for width in (320, 834, 390, 1024, 320):
            with self.subTest(width=width):
                owner.reflow(width)
                self.assertEqual(owner.reader_menu.enabled, not owner.wide)
                actions = [label for label, _ in owner.reader_actions.actions]
                self.assertEqual('Browse documentation' in actions, not owner.wide)
                if not owner.wide:
                    owner.reader_menu.on_press()
                    self.assertTrue(owner.sidebar.sidebar_open)
                    owner.reader_menu.on_press()
                    self.assertFalse(owner.sidebar.sidebar_open)
                self.assertEqual(owner.path, first.resolve())
