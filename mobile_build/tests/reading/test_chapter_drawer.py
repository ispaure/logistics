"""Chapter contents retain the page allocation and obey the E Ink policy."""
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import patch
import toga
from mobile.chapter_drawer import ChapterDrawer
from mobile.page_animation import sync_preferences


class ChapterDrawerTests(TestCase):
    def test_drawer_never_replaces_or_shrinks_the_page(self):
        app = NS(preferences=NS(values={'android_eink': 'false'}))
        sidebar, page = toga.Box(), toga.Box()
        drawer = ChapterDrawer(sidebar, page, app=app)
        with patch('mobile.chapter_drawer.SpeechOverlay') as overlay, \
                patch('commonUtils.ui.native.transitions.begin_page_slide') as begin, \
                patch('commonUtils.ui.native.transitions.finish_page_slide') as finish:
            for width in (390, 900):
                drawer.reflow(width)
                drawer.show_sidebar()
                self.assertEqual(list(drawer.view.children), [page])
                self.assertIsNone(sidebar.parent)
                self.assertFalse(drawer.expanded)
                self.assertTrue(drawer.sidebar_open)
                drawer.show_detail()
                self.assertFalse(drawer.sidebar_open)
            self.assertEqual(begin.call_count, 2)
            self.assertEqual(finish.call_count, 2)
            self.assertEqual(overlay.return_value.close.call_count, 2)
            app.preferences.values['android_eink'] = 'true'
            drawer.show_sidebar()
            self.assertEqual(begin.call_count, 2)
            self.assertEqual(finish.call_count, 2)
            # Native outside dismissal goes through the same controller state.
            sidebar.hide()
            self.assertFalse(drawer.sidebar_open)
            self.assertIsNone(sidebar.overlay)

    def test_enabling_eink_cancels_both_imported_and_provider_drawers(self):
        from unittest.mock import Mock
        imported, private = Mock(), Mock()
        app = NS(preferences=NS(values={'android_eink': 'true'}),
                 readers=NS(controllers={'a': NS(chapter_sidebar=imported)}),
                 private_sessions=NS(controllers={'b': NS(provider_epub_view=NS(sidebar=private))}))
        sync_preferences(app)
        imported.cancel_motion.assert_called_once()
        private.cancel_motion.assert_called_once()
