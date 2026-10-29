"""Generation publishes before dispatch and keeps failed turns recoverable."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from features.lm.domain import conversation, defaults, message
from features.lm.generation import GenerationCoordinator, GenerationInputs
from features.lm.session import ConversationSession
from features.lm.storage import Store


class GenerationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = Store(self.root / 'chat')
        self.session = ConversationSession(self.store)
        self.addCleanup(self.session.release_lease)
        self.session.create(conversation(defaults(), 'fixture', 'model'))
        self.session.data['draft'] = 'Question'
        self.session.data['messages'].append(message('user', 'Question'))
        self.client = Mock()
        from features.lm.execution.desktop import project_tools
        self.coordinator = GenerationCoordinator(self.session, self.client, project_tools=project_tools)
        self.inputs = GenerationInputs(dict(id='fixture', base_url='http://localhost:1234/v1'))

    def test_transport_and_ui_callback_observe_durable_pending_response(self):
        events = []
        def verify_saved():
            saved = self.store.load(self.session.data['id'])
            self.assertEqual(saved['messages'][-1]['status'], 'streaming')
            self.assertEqual(saved['draft'], '')
        def published():
            verify_saved()
            events.append('published')
        def dispatch(*args):
            verify_saved()
            events.append('dispatch')
        self.client.start.side_effect = dispatch
        result = self.coordinator.start(self.coordinator.prepare(self.inputs), 'session-secret',
                                        clear_draft=True, published=published)
        self.assertTrue(result.started)
        self.assertEqual(events, ['published', 'dispatch'])
        self.assertNotIn('session-secret', repr(vars(self.coordinator)))
        self.assertNotIn('session-secret', repr(self.store.load(self.session.data['id'])))

    def test_publication_failure_keeps_draft_and_never_starts_transport(self):
        plan = self.coordinator.prepare(self.inputs)
        snapshot = deepcopy(self.session.data)
        published = Mock()
        with patch.object(self.store, 'save', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.coordinator.start(plan, '', clear_draft=True, published=published)
        self.assertEqual(self.session.data, snapshot)
        published.assert_not_called()
        self.client.start.assert_not_called()

    def test_transport_start_failure_saves_retryable_user_turn(self):
        self.client.start.side_effect = OSError('offline')
        result = self.coordinator.start(self.coordinator.prepare(self.inputs), '',
                                        clear_draft=True, published=Mock())
        self.assertFalse(result.started)
        saved = self.store.load(self.session.data['id'])
        self.assertEqual(saved['messages'][0]['content'], 'Question')
        self.assertEqual(saved['messages'][-1]['status'], 'failed')
        self.assertIsNone(self.session.active_message)
        self.assertIsNone(result.save_error)

    def test_secondary_save_failure_keeps_failed_response_dirty(self):
        self.client.start.side_effect = OSError('offline')
        save = self.store.save
        count = 0
        def fail_second(data):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('disk full')
            return save(data)
        with patch.object(self.store, 'save', side_effect=fail_second):
            result = self.coordinator.start(self.coordinator.prepare(self.inputs), '',
                                            clear_draft=False, published=Mock())
        self.assertEqual(str(result.save_error), 'disk full')
        self.assertTrue(self.session.dirty)
        self.assertEqual(self.session.data['draft'], 'Question')
        self.session.save()
        self.assertEqual(self.store.load(self.session.data['id'])['messages'][-1]['status'], 'failed')

    def test_code_context_uses_captured_buffers_and_requires_project(self):
        self.session.data['mode'] = 'code'
        with self.assertRaisesRegex(ValueError, 'registered IDE project'):
            self.coordinator.prepare(self.inputs)
        project = SimpleNamespace(root=self.root, name='Fixture', id='project', excluded_paths=())
        plan = self.coordinator.prepare(GenerationInputs(self.inputs.profile, project, {'draft.py': 'unsaved'}))
        self.assertEqual(plan.project_tools.buffers['draft.py'], 'unsaved')
        self.assertEqual(plan.metadata['project_id'], 'project')
        self.assertTrue(plan.payload['tools'])
