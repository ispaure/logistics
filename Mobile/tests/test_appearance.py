"""Palette readability and matching offline document surfaces."""
import unittest
from logisticsmobile.appearance import contrast_ratio
from logisticsmobile.palette import LIGHT, DARK, argb, themed_chapter
from logisticsmobile.preview import markdown_preview
from logisticsmobile.chat_presentation import transcript_document


class AppearanceTests(unittest.TestCase):
    def test_text_and_secondary_labels_remain_readable_on_all_surfaces(self):
        for palette in (LIGHT, DARK):
            for surface in ('window', 'surface', 'alternate'):
                for ink in ('text', 'muted'):
                    with self.subTest(palette=palette, surface=surface, ink=ink):
                        self.assertGreaterEqual(contrast_ratio(argb(palette[ink]), argb(palette[surface])), 4.5)
            self.assertGreaterEqual(contrast_ratio(argb(palette['accent']), argb(palette['surface'])), 4.5)

    def test_preview_and_chat_follow_the_same_system_palette(self):
        for html in (markdown_preview('# Notes'), transcript_document()):
            self.assertIn('@media(prefers-color-scheme:dark)', html)
            for palette in (LIGHT, DARK):
                for role, color in palette.items():
                    self.assertIn(f'--{role}:{color}', html)
            self.assertIn('background:var(--surface)', html)

    def test_explicit_reader_appearance_overrides_device_mode(self):
        content = '<html><head><style>body{margin:24px}</style></head><body>Book</body></html>'
        for mode, palette in (('light', LIGHT), ('dark', DARK)):
            html = themed_chapter(content, mode)
            self.assertIn('body{margin:24px}', html)
            self.assertIn('<body>Book</body>', html)
            self.assertIn('--surface:' + palette['surface'], html)
            self.assertNotIn('@media', html)
