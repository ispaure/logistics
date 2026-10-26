"""Reader replacement is atomic with respect to stale tokens and preparation failure."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from mobile.reading.publication import ReadingPublication
from mobile.reading.sources import capture_library, capture_provider


class Surface:
    def __init__(self):
        self.disposed = False
    def dispose(self):
        self.disposed = True


class Container:
    def __init__(self, surface):
        self.children = [surface]
    def add(self, child):
        self.children.append(child)
    def remove(self, child):
        self.children.remove(child)


class ReadingPublicationTests(unittest.TestCase):
    def test_failed_preparation_keeps_display_and_stale_work_cannot_mount(self):
        old, new = Surface(), Surface()
        box = Container(old)
        current = [True]
        publication = ReadingPublication(SimpleNamespace(preferences=SimpleNamespace(values={})), box, lambda: current[0])
        def fail():
            raise ValueError('Synthetic decoding failure')
        with patch('mobile.page_animation.begin_page_slide'), patch('mobile.page_animation.finish_page_slide'), \
                patch('mobile.page_animation.cancel_page_slide') as cancel:
            with self.assertRaises(ValueError):
                publication.mount(new, publish=fail)
            self.assertEqual(box.children, [old])
            self.assertFalse(old.disposed)
            cancel.assert_called_once_with(box)
            current[0] = False
            self.assertFalse(publication.mount(new))
            self.assertTrue(new.disposed)
            self.assertEqual(box.children, [old])

    def test_failed_view_construction_releases_outgoing_animation(self):
        old = Surface()
        box = Container(old)
        publication = ReadingPublication(SimpleNamespace(preferences=SimpleNamespace(values={})), box, lambda: True)
        with patch('mobile.page_animation.begin_page_slide'), \
                patch('mobile.page_animation.cancel_page_slide') as cancel:
            with self.assertRaisesRegex(ValueError, 'native allocation'):
                with publication.preparing(1) as current:
                    self.assertTrue(current)
                    raise ValueError('native allocation')
            cancel.assert_called_once_with(box)
        self.assertFalse(publication.begun)
        self.assertFalse(old.disposed)
        self.assertEqual(box.children, [old])

    def test_replacement_retires_old_view_once_and_preserves_reserved_text(self):
        old, reserved, new = Surface(), Surface(), Surface()
        box = Container(old)
        publication = ReadingPublication(SimpleNamespace(preferences=SimpleNamespace(values={})), box, lambda: True)
        with patch('mobile.page_animation.begin_page_slide'), patch('mobile.page_animation.finish_page_slide'):
            self.assertTrue(publication.mount(new, keep=(reserved,), retired=(old, reserved)))
        self.assertTrue(old.disposed)
        self.assertFalse(reserved.disposed)
        self.assertEqual(box.children, [new])

    def test_retained_surface_is_published_without_native_detachment(self):
        surface = Surface()
        box = Container(surface)
        publication = ReadingPublication(SimpleNamespace(preferences=SimpleNamespace(values={})), box, lambda: True)
        published = []
        with patch.object(box, 'remove', side_effect=RuntimeError('In-flight native load detached')), \
                patch.object(box, 'add') as add, \
                patch('mobile.page_animation.begin_page_slide'), \
                patch('mobile.page_animation.finish_page_slide') as finish, \
                patch('mobile.page_animation.cancel_page_slide'):
            self.assertTrue(publication.mount(surface, direction=1, publish=lambda: published.append('updated')))
        self.assertEqual(published, ['updated'])
        add.assert_not_called()
        finish.assert_called_once_with(box, 1, {})
        self.assertEqual(box.children, [surface])
        self.assertFalse(surface.disposed)

    def test_source_tokens_reject_reader_replacement_and_closed_private_session(self):
        owner = SimpleNamespace(book_reader=object(), book_epoch=1, active_host=True)
        current = capture_library(owner)
        owner.book_epoch += 1
        self.assertFalse(current())
        valid = [True]
        owner = SimpleNamespace(active_host=True)
        view = SimpleNamespace(crypt_reader=object(), session=SimpleNamespace(id='synthetic'),
            workspace=SimpleNamespace(token=lambda key: key, accepts=lambda key: valid[0]))
        current = capture_provider(owner, view)
        self.assertTrue(current())
        valid[0] = False
        self.assertFalse(current())


class ProviderPresentationTests(unittest.TestCase):
    def comic(self):
        from unittest.mock import Mock
        navigation = SimpleNamespace(prepared=((0, 1), 0), crop=None, half=0,
                                     part_label='', commit=Mock())
        reader = SimpleNamespace(book=None, kind='.cbz', labels=['first', 'second'],
                                 comic_navigation=navigation, right_to_left=False)
        spread = Surface()
        spread.prepare_replacement = Mock(return_value=Mock())
        view = SimpleNamespace(crypt_reader=reader, crypt_content=Container(spread),
            provider_spread=spread, crypt_page=SimpleNamespace(value='second'),
            crypt_text=SimpleNamespace(value='preserved draft'), crypt_image=SimpleNamespace(image=None),
            crypt_title=SimpleNamespace(text='original title'), _provider_displayed_index=0)
        controller = SimpleNamespace(active_host=True, preferences=SimpleNamespace(values={}),
            private_comic_viewport=lambda view: (400, 800), private_comic_seam=lambda view: None,
            format_services=SimpleNamespace(seam_gap=lambda box: 0, page_region=lambda box: (400, 800)))
        return controller, view, spread

    def test_provider_decode_failure_preserves_visible_pixels_and_navigation_commit(self):
        from mobile.provider_ui import ProviderUI
        controller, view, old = self.comic()
        old.prepare_replacement.side_effect = ValueError('Synthetic decoding failure')
        with patch('features.comics.mobile.presentation.SpreadView', Surface), \
                patch('mobile.magnifier.bind'), patch('mobile.page_animation.begin_page_slide') as begin:
            with self.assertRaisesRegex(ValueError, 'Synthetic decoding failure'):
                ProviderUI._show_crypt_content(controller, 'spread', ((0, 1), b'new'), view=view)
        self.assertEqual(view.crypt_content.children, [old])
        self.assertFalse(old.disposed)
        self.assertEqual(view.crypt_title.text, 'original title')
        self.assertEqual(view.crypt_text.value, 'preserved draft')
        view.crypt_reader.comic_navigation.commit.assert_not_called()
        begin.assert_not_called()

    def test_provider_retired_during_placement_cannot_commit_prepared_spread(self):
        from mobile.provider_ui import ProviderUI
        controller, view, old = self.comic()
        publish = old.prepare_replacement.return_value
        def retire(*args):
            controller.active_host = False
        with patch('features.comics.mobile.presentation.SpreadView', Surface), \
                patch('mobile.magnifier.bind'), patch('mobile.page_animation.begin_page_slide'), \
                patch('mobile.page_animation.cancel_page_slide') as cancel, \
                patch('features.comics.mobile.presentation.place_page', side_effect=retire), \
                patch.object(ReadingPublication, 'chrome') as chrome:
            ProviderUI._show_crypt_content(controller, 'spread', ((0, 1), b'new'), view=view)
        publish.assert_not_called()
        view.crypt_reader.comic_navigation.commit.assert_not_called()
        self.assertEqual(view.crypt_content.children, [old])
        self.assertFalse(old.disposed)
        self.assertEqual(view.crypt_text.value, 'preserved draft')
        self.assertEqual(view._provider_displayed_index, 0)
        cancel.assert_called()
        chrome.assert_not_called()

    def test_provider_epub_fallback_preserves_anchor_bookmarks_and_motion_callbacks(self):
        from unittest.mock import Mock
        import toga
        from mobile.provider_presentation import prepare_epub_page
        button = toga.Button('Tools')
        panel = SimpleNamespace(text=toga.MultilineTextInput(), tools=SimpleNamespace(
            button=button, widget=toga.Box(children=[button]), panel=toga.Box()),
            chapters=SimpleNamespace(render=Mock()))
        host = SimpleNamespace(preferences=SimpleNamespace(values={
            'reading_theme': 'light', 'epub_font_size': '18', 'reading_margin': '12'}))
        controller = SimpleNamespace(_provider_epub_target='section', open_provider_epub_chapter=Mock())
        chapter = SimpleNamespace(anchors={'section': 21}, length=200)
        view = SimpleNamespace(crypt_reader=SimpleNamespace(book=SimpleNamespace(spine=['one', 'two']),
            labels=['one', 'two']), crypt_page=SimpleNamespace(value='two'),
            crypt_bookmark_button=toga.Button('Bookmark'), crypt_bookmark_selector=toga.Selection(items=[]),
            page_footer=SimpleNamespace(chapter_progress=Mock()))
        with patch('features.books.mobile.provider_reader.provider_view', return_value=panel) as factory, \
                patch('mobile.font_scaling.bind') as bind, \
                patch('mobile.page_animation.begin_page_slide') as begin, \
                patch('mobile.page_animation.finish_page_slide') as finish:
            self.assertIs(prepare_epub_page(host, controller, view, ('<p>Text</p>', chapter)), panel)
            self.assertEqual(factory.call_args.kwargs['offset'], 21)
            self.assertIs(factory.call_args.kwargs['on_chapter'], controller.open_provider_epub_chapter)
            factory.call_args.kwargs['on_position'](32)
            self.assertEqual(view._provider_epub_locations, {'two': 32})
            view.page_footer.chapter_progress.assert_called_once_with(1, 2, 32, 200)
            self.assertIsNone(controller._provider_epub_target)
            bind.assert_called_once_with(host, panel.text, 'epub')
            self.assertNotIn(button, panel.tools.widget.children)
            self.assertIs(view.crypt_bookmark_button.parent, panel.tools.panel)
            self.assertIs(view.crypt_bookmark_selector.parent, panel.tools.panel)
            surface = object()
            panel.page_motion[0](surface, 1)
            panel.page_motion[1](surface, 1)
            begin.assert_called_once_with(surface, 1, host.preferences.values)
            finish.assert_called_once_with(surface, 1, host.preferences.values)
        self.assertTrue(panel.page_motion_enabled())
        host.preferences.values['android_eink'] = 'true'
        self.assertFalse(panel.page_motion_enabled())
