"""Shared stream decoding retains mobile policy without importing Qt."""
from io import BytesIO
import json
import unittest
from unittest.mock import Mock, patch

from features.lm.streaming import StreamDecoder
from features.lm.mobile.transport import ChatClient


def event(value):
    return ('data: ' + json.dumps(value) + '\n\n').encode()


class SharedStreamTests(unittest.TestCase):
    def test_reasoning_fields_stream_separately_from_answer_across_utf8_boundaries(self):
        wire = event(dict(choices=[dict(delta=dict(reasoning='Planning é. '))]))
        wire += event(dict(choices=[dict(delta=dict(reasoning_content='Checking.'))]))
        wire += event(dict(choices=[dict(delta=dict(content='Final answer'), finish_reason='stop')]))
        decoder = StreamDecoder()
        answer = ''.join(decoder.feed(wire[i:i + 3]) for i in range(0, len(wire), 3))
        self.assertEqual(answer, 'Final answer')
        self.assertEqual(decoder.reasoning_text, 'Planning é. Checking.')

    def test_reasoning_is_bounded_and_rejects_unsupported_structures(self):
        for delta in (dict(reasoning={'text': 'wrong shape'}), dict(reasoning='x' * 20, content='y' * 20)):
            with self.subTest(delta=delta), patch('features.lm.streaming.MAX_TEXT', 30), self.assertRaises(ValueError):
                StreamDecoder().feed(event(dict(choices=[dict(delta=delta)])))

    def test_desktop_chunks_and_mobile_lines_produce_the_same_reply(self):
        wire = event(dict(choices=[dict(delta=dict(content='Hello é'))]))
        wire += event(dict(choices=[dict(delta={}, finish_reason='stop')]))
        wire += b'data: [DONE]\n\n'
        decoder = StreamDecoder()
        fragments = [decoder.feed(wire[i:i + 3]) for i in range(0, len(wire), 3)]
        client = ChatClient('http://127.0.0.1/v1')
        connection, response = Mock(), BytesIO(wire)
        client.request = Mock(return_value=(connection, response))
        mobile = []
        self.assertEqual(client._stream({}, mobile.append), decoder.finish_reason)
        self.assertEqual(''.join(mobile), ''.join(fragments))
        self.assertEqual(''.join(mobile), 'Hello é')
        self.assertTrue(response.closed)
        connection.close.assert_called_once()

    def test_mobile_single_choice_and_legacy_tool_rejection(self):
        for choices in ([dict(delta={}), dict(delta={})],
                        [dict(delta=dict(function_call=dict(name='tool')))]):
            client = ChatClient('http://127.0.0.1/v1')
            response = BytesIO(event(dict(choices=choices)))
            client.request = Mock(return_value=(Mock(), response))
            with self.subTest(choices=choices), self.assertRaises(ValueError):
                client._stream({}, lambda text: None)
            self.assertTrue(response.closed)

    def test_mobile_reply_limit_keeps_only_already_published_fragments(self):
        wire = event(dict(choices=[dict(delta=dict(content='x' * 40000))])) * 7
        client = ChatClient('http://127.0.0.1/v1')
        response = BytesIO(wire)
        client.request = Mock(return_value=(Mock(), response))
        fragments = []
        with self.assertRaisesRegex(ValueError, '256 KiB'):
            client._stream({}, fragments.append)
        self.assertEqual(len(''.join(fragments)), 240000)
        self.assertTrue(response.closed)
