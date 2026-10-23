"""Project scope, limits and editor snapshots for read-only LM context."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from features.lm.project_tools import ProjectTools, MAX_FILE_BYTES, TOOLS
from features.lm.domain import build_request, conversation, message, validate_conversation


class ProjectToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = SimpleNamespace(root=self.root, name='Fixture', excluded_paths=['private', 'nested/skip'])
        (self.root / 'main.py').write_text('disk value\nsecond line\n')
        (self.root / 'private').mkdir()
        (self.root / 'private' / 'secret.txt').write_text('hidden value')
        (self.root / 'nested' / 'skip').mkdir(parents=True)
        (self.root / 'nested' / 'skip' / 'hidden.py').write_text('hidden value')
        self.tools = ProjectTools(self.project, {'main.py': 'unsaved value\nsecond line\n'})

    def call(self, name, **args):
        return json.loads(self.tools.execute(name, json.dumps(args)))

    def test_reads_editor_snapshot_with_line_numbers(self):
        result = self.call('read_file', path='main.py', start_line=1, end_line=1)
        self.assertEqual(result['text'], '1: unsaved value')
        self.assertEqual(result['source'], 'editor snapshot')
        self.assertEqual((self.root / 'main.py').read_text(), 'disk value\nsecond line\n')

    def test_searches_content_and_paths_without_exclusions(self):
        result = self.call('search_files', query='VALUE')
        self.assertEqual(result['matches'], [dict(path='main.py', line=1, text='unsaved value')])
        self.assertEqual(self.call('list_files', query='.py')['matches'], ['main.py'])

    def test_rejects_escape_exclusions_symlinks_and_unknown_tools(self):
        outside = self.root.parent / 'outside'
        (self.root / 'link').symlink_to(outside)
        (self.root / 'linked-dir').symlink_to(self.root / 'private', target_is_directory=True)
        for path in ('../outside', str(outside), 'private/secret.txt', 'nested/skip/hidden.py', 'link', 'linked-dir/secret.txt'):
            with self.subTest(path=path):
                self.assertIn('error', self.call('read_file', path=path, start_line=1, end_line=1))
        self.assertIn('error', self.call('write_file', path='main.py', content='changed'))
        self.assertNotIn('linked-dir/secret.txt', self.call('list_files', query='')['matches'])

    def test_bounds_files_results_and_lines_and_rejects_binary(self):
        (self.root / 'binary').write_bytes(b'\0binary')
        (self.root / 'huge').write_bytes(b'x' * (MAX_FILE_BYTES + 1))
        (self.root / 'long').write_text('x' * 20000)
        for path in ('binary', 'huge'):
            self.assertIn('error', self.call('read_file', path=path, start_line=1, end_line=1))
        self.assertIn('error', self.call('read_file', path='main.py', start_line=1, end_line=201))
        result = self.call('read_file', path='long', start_line=1, end_line=1)
        self.assertTrue(result['truncated'])
        self.assertEqual(len(result['text']), 10000)
        self.assertEqual(json.loads(self.tools.execute('list_files', '{broken'))['error'][:8], 'Expectin')
        self.assertEqual(json.loads(self.tools.execute('list_files', '{"query":""}', cancelled=lambda: True))['matches'], [])

    def test_legacy_chat_and_code_request_budget_and_persistence(self):
        data = conversation(dict(context_tokens=8192, max_tokens=1024, temperature=None, top_p=None, system_prompt='Help'))
        data['model'] = 'fixture'
        data['messages'] = [message('user', 'Explain this project')]
        self.assertIs(validate_conversation(data), data)
        chat, _ = build_request(data)
        self.assertNotIn('tools', chat)
        data.update(mode='code', project_id='registration-id')
        self.assertIs(validate_conversation(data), data)
        payload, metadata = build_request(data, tools=TOOLS, project_name='Fixture')
        self.assertEqual(payload['tools'], TOOLS)
        self.assertIn('Fixture', payload['messages'][0]['content'])
        self.assertGreater(metadata['estimated_input_tokens'], build_request(data)[1]['estimated_input_tokens'])
        data['settings']['context_tokens'] = 1300
        with self.assertRaises(ValueError):
            build_request(data, tools=TOOLS, project_name='Fixture')
