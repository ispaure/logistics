"""LM context, persistence and stream framing regression contracts."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from features.lm.domain import base_url, build_request, conversation, message, validate_settings
from features.lm.storage import ConflictError, Store, export_markdown
from features.lm.transport import StreamDecoder


def settings(**values):
    return dict(context_tokens=8192, max_tokens=1024, temperature=None, top_p=None,
                system_prompt='Be helpful.', **values)


class ContextTests(unittest.TestCase):
    def make(self):
        data = conversation(settings(), 'local', 'test-model')
        data['messages'] = [message('user', 'Hello'), message('assistant', 'Hi'), message('user', 'Remember my first message?')]
        return data

    def test_reopened_history_and_sampling_controls(self):
        data = self.make()
        data['settings']['temperature'] = .4
        payload, metadata = build_request(data)
        self.assertEqual([m['role'] for m in payload['messages']], ['system', 'user', 'assistant', 'user'])
        self.assertEqual(payload['temperature'], .4)
        self.assertNotIn('top_p', payload)
        self.assertEqual(metadata['message_ids'], [m['id'] for m in data['messages']])
        self.assertEqual(metadata['omitted_turns'], 0)

    def test_context_trims_whole_turns_without_mutating_history(self):
        data = self.make()
        data['settings'].update(context_tokens=256, max_tokens=128)
        data['messages'][0]['content'] = 'x' * 2000
        before = deepcopy(data)
        payload, metadata = build_request(data)
        self.assertEqual(len(payload['messages']), 2)
        self.assertEqual(metadata['omitted_turns'], 1)
        self.assertEqual(data, before)

    def test_latest_prompt_is_never_silently_truncated(self):
        data = self.make()
        data['messages'][-1]['content'] = 'x' * 100000
        with self.assertRaisesRegex(ValueError, 'exceed'):
            build_request(data)

    def test_failed_turns_are_excluded_and_regeneration_uses_latest_complete_alternative(self):
        data = self.make()
        data['messages'][1]['status'] = 'cancelled'
        payload, _ = build_request(data)
        self.assertEqual([m['content'] for m in payload['messages']], ['Be helpful.', 'Remember my first message?'])
        replacement = message('assistant', 'A better answer')
        data['messages'].insert(2, replacement)
        payload, metadata = build_request(data)
        self.assertEqual(payload['messages'][2]['content'], replacement['content'])
        self.assertIn(replacement['id'], metadata['message_ids'])
        self.assertNotIn(data['messages'][1]['id'], metadata['message_ids'])

    def test_identical_text_does_not_confuse_selected_message_ids(self):
        data = self.make()
        data['messages'].insert(2, message('assistant', 'Hi'))
        _, metadata = build_request(data)
        self.assertNotIn(data['messages'][1]['id'], metadata['message_ids'])
        self.assertIn(data['messages'][2]['id'], metadata['message_ids'])

    def test_validate_numbers_and_urls(self):
        for key, value in [('temperature', float('nan')), ('top_p', 1.5), ('max_tokens', True)]:
            values = settings()
            values[key] = value
            with self.assertRaises(ValueError):
                validate_settings(values)
        for url in ('file:///tmp', 'http://secret@localhost/v1', 'http://localhost/v1?token=secret', 'http://localhost:bad'):
            with self.assertRaises(ValueError):
                base_url(url)
        self.assertEqual(base_url('http://localhost:1234/v1/'), 'http://localhost:1234/v1')


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def test_drafts_and_interrupted_output_survive_restart(self):
        data = conversation(settings(), 'local', 'test')
        data['draft'] = 'Next question'
        data['messages'] = [message('user', 'hello'), message('assistant', 'Partial', 'streaming')]
        self.store.save(data)
        saved = Store(self.temp.name).load(data['id'])
        self.assertEqual(saved['draft'], 'Next question')
        self.assertEqual(saved['messages'][1]['status'], 'streaming')
        self.assertEqual(saved['messages'][1]['content'], 'Partial')

    def test_concurrent_writes_and_deleted_records_do_not_overwrite(self):
        data = conversation(settings())
        self.store.save(data)
        stale = deepcopy(data)
        data['title'] = 'New title'
        self.store.save(data)
        with self.assertRaises(ConflictError):
            self.store.save(stale)
        self.assertEqual(self.store.load(data['id'])['title'], 'New title')
        self.store.delete(data)
        with self.assertRaises(ConflictError):
            self.store.save(data)

    def test_lease_prevents_two_editors(self):
        data = conversation(settings())
        first = self.store.lease(data['id'])
        try:
            with self.assertRaises(ConflictError):
                self.store.lease(data['id'])
        finally:
            first.unlock()
        second = self.store.lease(data['id'])
        second.unlock()

    def test_malformed_and_future_files_are_preserved(self):
        self.store.folder.mkdir(parents=True)
        key = 'a' * 32
        path = self.store.path(key)
        for content in ('{invalid', json.dumps({'schema_version': 999})):
            path.write_text(content)
            records, warnings = self.store.list()
            self.assertEqual(records, [])
            self.assertTrue(warnings)
            self.assertEqual(path.read_text(), content)

    def test_atomic_failure_keeps_old_file_and_revision(self):
        data = conversation(settings())
        self.store.save(data)
        original = self.store.path(data['id']).read_bytes()
        revision = data['revision']
        data['title'] = 'Pending'
        with patch('commonUtils.persistence.os.replace', side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):
                self.store.save(data)
        self.assertEqual(self.store.path(data['id']).read_bytes(), original)
        self.assertEqual(data['revision'], revision)
        self.assertEqual(len(list(self.store.folder.iterdir())), 1)

    def test_profiles_never_save_tokens_and_detect_stale_edits(self):
        original = self.store.profiles()
        changed = deepcopy(original)
        changed[0].update(name='Office', token='secret-token')
        self.store.save_profiles(changed, original)
        self.assertNotIn('secret-token', (self.store.root / 'profiles.json').read_text())
        with self.assertRaises(ConflictError):
            self.store.save_profiles(original, original)

    def test_search_and_export_keep_cancelled_response(self):
        data = conversation(settings())
        data['messages'] = [message('user', 'Paris'), message('assistant', 'Partial answer', 'cancelled')]
        self.store.save(data)
        self.assertEqual(len(self.store.list('paris')[0]), 1)
        self.assertIn('Assistant (cancelled)', export_markdown(data))
        self.assertIn('Partial answer', export_markdown(data))

    def test_nested_folders_mirror_json_placement_and_reopen(self):
        data = conversation(settings())
        data['folder'] = 'Projects/Planning/2026'
        data['messages'] = [message('user', 'Nested conversation')]
        self.store.save(data)
        path = self.store.folder / 'Projects/Planning/2026' / (data['id'] + '.json')
        self.assertTrue(path.is_file())
        reopened = Store(self.temp.name).load(data['id'])
        self.assertEqual(reopened['folder'], 'Projects/Planning/2026')
        self.assertEqual(self.store.list('nested')[0][0]['id'], data['id'])
        self.assertEqual(self.store.folders(), ['Projects', 'Projects/Planning', 'Projects/Planning/2026'])
        self.store.save(reopened)
        self.assertTrue(path.is_file())
        self.assertFalse((self.store.folder / path.name).exists())

    def test_move_preserves_history_draft_and_identity_and_invalidates_stale_copy(self):
        data = conversation(settings())
        data['draft'] = 'Keep my draft'
        data['messages'] = [message('user', 'hello'), message('assistant', 'Answer')]
        self.store.save(data)
        old_path = self.store.path(data['id'])
        stale = deepcopy(data)
        self.store.move(data, 'Work/Deep/Nested')
        self.assertFalse(old_path.exists())
        self.assertEqual(self.store.load(data['id'])['draft'], 'Keep my draft')
        self.assertEqual(self.store.load(data['id'])['messages'], stale['messages'])
        with self.assertRaises(ConflictError):
            self.store.save(stale)
        self.store.move(data, '')
        self.assertTrue(old_path.exists())
        self.assertEqual(len(self.store.list()[0]), 1)

    def test_move_failure_preserves_source_and_revision(self):
        data = conversation(settings())
        self.store.save(data)
        original = deepcopy(data)
        path = self.store.path(data['id'])
        with patch('commonUtils.persistence.os.link', side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):
                self.store.move(data, 'Nested/Folder')
        self.assertEqual(data, original)
        self.assertEqual(self.store.load(data['id']), original)
        self.assertTrue(path.is_file())

    def test_move_source_retirement_failure_rolls_back_destination(self):
        data = conversation(settings())
        self.store.save(data)
        source = self.store.path(data['id'])
        original = deepcopy(data)
        unlink = Path.unlink
        def fail_source(path, *args, **kwargs):
            if path == source:
                raise OSError('Cannot retire source')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail_source):
            with self.assertRaisesRegex(OSError, 'retire source'):
                self.store.move(data, 'Destination')
        self.assertTrue(source.exists())
        self.assertFalse((self.store.folder / 'Destination' / source.name).exists())
        self.assertEqual(data, original)
        self.assertEqual(self.store.load(data['id']), original)

    def test_move_cannot_bypass_another_window_edit_lease(self):
        data = conversation(settings())
        self.store.save(data)
        lease = self.store.lease(data['id'])
        try:
            with self.assertRaises(ConflictError):
                self.store.move(data, 'Other')
            self.store.move(data, 'Other', lease=lease)
            with self.assertRaises(ConflictError):
                self.store.lease(data['id'])
        finally:
            lease.unlock()

    def test_folder_escape_and_symlinks_are_rejected(self):
        for name in ('/tmp', '../outside', 'Work/../Outside', 'Work//Nested', r'Work\Other', 'CON', 'Ends.'):
            with self.assertRaises(ValueError):
                self.store.create_folder(name)
        self.store.create_folder('Valid')
        with TemporaryDirectory() as outside:
            (self.store.folder / 'Link').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.store.create_folder('Link/Nested')
            self.assertNotIn('Link', self.store.folders())

    def test_duplicate_ids_in_different_folders_are_preserved_and_reported(self):
        data = conversation(settings())
        self.store.save(data)
        duplicate = self.store.create_folder('Copy') / (data['id'] + '.json')
        duplicate.write_bytes(self.store.path(data['id']).read_bytes())
        records, warnings = self.store.list()
        self.assertEqual(records, [])
        self.assertEqual(len(warnings), 2)
        with self.assertRaises(ConflictError):
            self.store.load(data['id'])
        self.assertTrue(duplicate.exists())

    def test_physical_folder_wins_when_existing_json_is_moved_manually(self):
        data = conversation(settings())
        self.store.save(data)
        old = self.store.path(data['id'])
        target = self.store.create_folder('Manual/Placement') / old.name
        old.rename(target)
        loaded = self.store.load(data['id'])
        self.assertEqual(loaded['folder'], 'Manual/Placement')
        with self.assertRaises(ConflictError):
            self.store.save(data)
        self.store.delete(loaded)
        self.assertFalse(target.exists())


class DecoderTests(unittest.TestCase):
    def test_fragmented_utf8_crlf_and_usage(self):
        text = 'Bonjour 🌍'
        event = json.dumps({'choices': [{'delta': {'content': text}, 'finish_reason': None}]}, ensure_ascii=False)
        wire = (': heartbeat\r\n\r\ndata: ' + event + '\r\n\r\n' +
                'data: {"choices":[],"usage":{"total_tokens":12}}\n\n' +
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n' +
                'data: [DONE]\n\n').encode()
        decoder = StreamDecoder()
        received = ''.join(decoder.feed(bytes([byte])) for byte in wire)
        self.assertEqual(received, text)
        self.assertTrue(decoder.done)
        self.assertTrue(decoder.finished)
        self.assertEqual(decoder.usage['total_tokens'], 12)

    def test_stream_truncation_remains_detectable(self):
        decoder = StreamDecoder()
        decoder.feed(b'data: {"choices":[{"delta":{"content":"Partial"}}]}\n\n')
        self.assertEqual(decoder.text, 'Partial')
        self.assertFalse(decoder.done or decoder.finished)

    def test_invalid_records_and_tools_are_rejected(self):
        for wire in (b'data: {bad}\n\n', b'data: {"error":"secret"}\n\n',
                     b'data: {"choices":[{"delta":{"tool_calls":[{}]}}]}\n\n'):
            with self.assertRaises(ValueError):
                StreamDecoder().feed(wire)


if __name__ == '__main__':
    unittest.main()
