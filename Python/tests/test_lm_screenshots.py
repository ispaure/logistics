"""Portable screenshot records and multimodal request context contracts."""
from copy import deepcopy
import base64
import struct
import unittest
from uuid import uuid4
from features.lm.screenshots import validate_images, image_url, IMAGE_TOKENS
from features.lm.domain import conversation, message, build_request, message_tokens, validate_conversation


class ScreenshotTests(unittest.TestCase):
    def setUp(self):
        self.image = dict(id=uuid4().hex, mime='image/png', width=1, height=1,
            data='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aGfkAAAAASUVORK5CYII=')
        self.data = conversation(dict(context_tokens=8192, max_tokens=1024, temperature=None, top_p=None, system_prompt='Help'), model='fixture')

    def test_screenshot_records_are_optional_and_validated_in_messages_and_drafts(self):
        validate_conversation(self.data)
        self.data['draft_images'] = [self.image]
        self.data['messages'] = [message('user', '', images=[self.image])]
        self.assertIs(validate_conversation(self.data), self.data)
        for invalid in (dict(self.image, mime='image/svg+xml'), dict(self.image, data='not base64'),
                        dict(self.image, width=9000), dict(self.image, id='bad')):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_images([invalid])
        for invalid in ([self.image] * 5, [self.image, self.image], {'data': 'bad'}):
            with self.assertRaises(ValueError):
                validate_images(invalid)
        content = bytearray(base64.b64decode(self.image['data']))
        content[16:20] = struct.pack('>I', 999999)
        with self.assertRaises(ValueError):
            validate_images([dict(self.image, width=999999, data=base64.b64encode(content).decode())])

    def test_screenshot_turns_reappear_whole_in_context_and_use_image_reserve(self):
        self.data['messages'] = [message('user', 'Describe', images=[self.image])]
        payload, metadata = build_request(self.data)
        parts = payload['messages'][-1]['content']
        self.assertEqual(parts[0], dict(type='text', text='Describe'))
        self.assertEqual(parts[1], dict(type='image_url', image_url=dict(url=image_url(self.image))))
        self.assertGreater(metadata['estimated_input_tokens'], IMAGE_TOKENS)
        self.data['messages'] += [message('assistant', 'A screenshot'), message('user', 'Continue')]
        payload, _ = build_request(self.data)
        self.assertEqual(payload['messages'][1]['content'], parts)
        self.assertIsInstance(payload['messages'][-1]['content'], str)
        self.data['settings']['context_tokens'] = 1800
        payload, metadata = build_request(self.data)
        self.assertEqual(metadata['omitted_turns'], 1)
        self.assertEqual([m['role'] for m in payload['messages']], ['system', 'user'])
        self.data['messages'] = [message('user', '', images=[self.image])]
        with self.assertRaises(ValueError):
            build_request(self.data)

    def test_image_budgets_do_not_count_base64_as_text(self):
        small = dict(role='user', content=[dict(type='image_url', image_url=dict(url=image_url(self.image)))])
        large = deepcopy(small)
        large['content'][0]['image_url']['url'] += 'a' * 100000
        self.assertEqual(message_tokens(small), message_tokens(large))
