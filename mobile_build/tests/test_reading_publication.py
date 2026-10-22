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
        with patch('mobile.page_animation.begin_page_slide'), patch('mobile.page_animation.finish_page_slide'):
            with self.assertRaises(ValueError):
                publication.mount(new, publish=fail)
            self.assertEqual(box.children, [old])
            self.assertFalse(old.disposed)
            current[0] = False
            self.assertFalse(publication.mount(new))
            self.assertTrue(new.disposed)
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
