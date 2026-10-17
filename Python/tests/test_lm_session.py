"""Edit ownership and response publication without constructing chat widgets."""
from copy import deepcopy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from features.lm.domain import conversation, defaults, message
from features.lm.session import ConversationSession
from features.lm.storage import Store


class ConversationSessionTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = Store(temporary.name)
        self.session = ConversationSession(self.store)
        self.addCleanup(self.session.release_lease)
        self.session.create(conversation(defaults()))

    def test_failed_open_retains_current_owner_and_releases_attempted_lease(self):
        original, lease = self.session.data, self.session.lease
        target = conversation(defaults())
        self.store.save(target)
        with patch.object(self.store, 'load', side_effect=OSError('Unreadable record')):
            with self.assertRaises(OSError):
                self.session.open(target['id'])
        self.assertIs(self.session.data, original)
        self.assertIs(self.session.lease, lease)
        available = self.store.lease(target['id'])
        available.unlock()
        with self.assertRaises(ValueError):
            self.store.lease(original['id'])

    def test_failed_creation_keeps_previous_record_and_releases_new_lease(self):
        original, lease = self.session.data, self.session.lease
        target = conversation(defaults())
        with patch.object(self.store, 'save', side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):
                self.session.create(target)
        self.assertIs(self.session.data, original)
        self.assertIs(self.session.lease, lease)
        available = self.store.lease(target['id'])
        available.unlock()

    def test_recovery_requires_lease_and_remains_dirty_until_saved(self):
        self.session.data['messages'] = [message('assistant', 'Partial', status='streaming')]
        self.session.dirty = True
        self.session.save()
        key = self.session.data['id']
        competing = ConversationSession(self.store)
        with self.assertRaises(ValueError):
            competing.open(key)
        self.assertEqual(self.store.load(key)['messages'][0]['status'], 'streaming')
        self.session.release_lease()
        self.assertTrue(self.session.open(key))
        self.assertTrue(self.session.dirty)
        self.assertEqual(self.session.data['messages'][0]['status'], 'interrupted')
        self.session.save()
        self.assertEqual(self.store.load(key)['messages'][0]['status'], 'interrupted')

    def test_failed_response_publication_restores_draft_and_never_activates(self):
        self.session.data['draft'] = 'Keep my question'
        self.session.data['messages'].append(message('user', 'Keep my question'))
        snapshot = deepcopy(self.session.data)
        with patch.object(self.store, 'save', side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):
                self.session.begin_response({})
        self.assertEqual(self.session.data, snapshot)
        self.assertIsNone(self.session.active_message)
        self.assertTrue(self.session.dirty)

    def test_retry_preserves_draft_and_previous_answer_then_saves_partial_output(self):
        self.session.data['draft'] = 'Next question'
        self.session.data['messages'] = [message('user', 'Question'), message('assistant', 'First answer')]
        self.session.begin_response({}, clear_draft=False)
        key = self.session.data['id']
        published = self.store.load(key)
        self.assertEqual(published['draft'], 'Next question')
        self.assertEqual(published['messages'][1]['content'], 'First answer')
        self.assertEqual(published['messages'][-1]['status'], 'streaming')
        self.assertTrue(self.session.append_delta('Partial retry'))
        self.assertTrue(self.session.complete_response('cancelled', '', {'finish_reason': None}))
        self.assertIsNone(self.session.active_message)
        with patch.object(self.store, 'save', side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):
                self.session.save()
        self.assertTrue(self.session.dirty)
        self.session.save()
        saved = self.store.load(key)
        self.assertEqual(saved['messages'][-1]['status'], 'cancelled')
        self.assertEqual(saved['messages'][-1]['content'], 'Partial retry')
        self.assertFalse(self.session.append_delta('Late signal'))
        self.assertFalse(self.session.complete_response('complete', '', {}))


if __name__ == '__main__':
    unittest.main()
