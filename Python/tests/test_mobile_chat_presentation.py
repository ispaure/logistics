"""Inert message formatting and bounded mobile composer layout."""
import unittest

from features.lm.domain import message
from features.lm.mobile.presentation import composer_height, transcript_document, transcript_entries, transcript_update


class MobileChatPresentationTests(unittest.TestCase):
    def test_untrusted_reply_markup_and_user_markdown_stay_inert(self):
        text = '<script>window.bad = true</script>\n<img src="https://invalid.test/x">\n**Bold**\n`code`'
        entries = transcript_entries([message('user', text), message('assistant', text)])
        self.assertIn('**Bold**', entries[0]['html'])
        self.assertIn('<strong>Bold</strong>', entries[1]['html'])
        self.assertIn('<code>code</code>', entries[1]['html'])
        for entry in entries:
            self.assertNotIn('<script>', entry['html'])
            self.assertNotIn('<img ', entry['html'])
        self.assertNotIn('<script', transcript_document())
        self.assertIn("default-src 'none'", transcript_document())

    def test_recovered_and_partial_replies_have_visible_status(self):
        entries = transcript_entries([message('assistant', 'Partial', 'interrupted'),
                                      message('assistant', '', 'streaming')])
        self.assertEqual(entries[0]['label'], 'Assistant · Interrupted')
        self.assertIn('Waiting for a reply', entries[1]['html'])
        update = transcript_update('conversation', entries, 20, configured=True)
        self.assertIn('"font_size": 20', update)
        self.assertIn('"force_latest": false', update)

    def test_composer_grows_for_wrapped_lines_and_stays_bounded(self):
        self.assertEqual(composer_height('', 220), 52)
        self.assertGreater(composer_height('Line\nLine\nLine', 220), 52)
        self.assertGreaterEqual(composer_height('A' * 100, 160), composer_height('A' * 100, 390))
        self.assertGreaterEqual(composer_height('漢' * 50, 220), composer_height('a' * 50, 220))
        self.assertEqual(composer_height('Long\n' * 1000, 220, 24), 120)
        # Keyboard-reduced phone viewports retain room for header/navigation;
        # long drafts scroll inside the composer instead of covering Send.
        self.assertEqual(composer_height('Long\n' * 1000, 220, available_height=260), 65)
        self.assertEqual(composer_height('Long\n' * 1000, 220, available_height=160), 52)
        self.assertEqual(composer_height('Long\n' * 1000, 220, available_height=800), 120)

    def test_streaming_reuses_completed_blocks_and_sends_only_the_changed_tail(self):
        messages = [message('user', 'A completed turn'), message('assistant', 'Partial', 'streaming')]
        before = transcript_entries(messages)
        messages[-1]['content'] += ' reply'
        after = transcript_entries(messages, before)
        self.assertIs(after[0], before[0])
        self.assertIsNot(after[1], before[1])
        update = transcript_update('conversation', after[1:], 16, configured=True, start=1)
        self.assertNotIn('A completed turn', update)
        self.assertIn('"count": 2', update)

    def test_assistant_lists_and_unclosed_code_fences_render_as_readable_blocks(self):
        entries = transcript_entries([message('assistant', '1. **First**\n2. Second\n\n```python\nprint("hello")')])
        self.assertIn('<ol>\n<li><strong>First</strong></li>\n<li>Second</li>\n</ol>', entries[0]['html'])
        self.assertIn('&quot;hello&quot;', entries[0]['html'])
        self.assertTrue(entries[0]['html'].rstrip().endswith('</code></pre>'))


class NavigationClearanceTests(unittest.TestCase):
    def test_floating_bar_and_keyboard_use_actual_overlap(self):
        from features.lm.mobile.presentation import navigation_clearance
        self.assertEqual(navigation_clearance(116, 840, 790, 64), 62)
        self.assertEqual(navigation_clearance(116, 546, 496, 64), 62)
        self.assertEqual(navigation_clearance(116, 546, 790, 64), 12)
        self.assertEqual(navigation_clearance(116, 546, 0, 64), 12)
        self.assertEqual(navigation_clearance(82, 778, 204, 574, bar_width=52), 12)
        self.assertEqual(navigation_clearance(116, 840, 790, 64, bar_width=350), 62)


if __name__ == '__main__':
    unittest.main()
