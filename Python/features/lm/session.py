"""Conversation edit ownership and response state, independent of desktop widgets.

The caller collects UI values before saving, checks transport availability before
switching records, and retains this owner until asynchronous work has settled.
Store failures propagate so the presentation can offer retry/export/discard.
"""
from copy import deepcopy

from .domain import message


class ConversationSession:
    def __init__(self, store):
        self.store = store
        self.data = None
        self.lease = None
        self.dirty = False
        self.active_message = None

    def open(self, key):
        """Acquire/load before replacing the current record; report recovery."""
        lease = self.store.lease(key)
        try:
            data = self.store.load(key)
        except BaseException:
            lease.unlock()
            raise
        self._adopt(data, lease)
        interrupted = False
        for entry in data['messages']:
            if entry['status'] == 'streaming':
                entry['status'] = 'interrupted'
                interrupted = True
        self.dirty = interrupted
        return interrupted

    def create(self, data):
        """Publish a new record before surrendering the previous edit lease."""
        lease = self.store.lease(data['id'])
        try:
            self.store.save(data)
        except BaseException:
            lease.unlock()
            raise
        self._adopt(data, lease)

    def _adopt(self, data, lease):
        self.release_lease()
        self.data, self.lease = data, lease
        self.dirty = False
        self.active_message = None

    def release_lease(self):
        """Idempotent, including when called after the view has been destroyed."""
        if self.lease is not None:
            self.lease.unlock()
            self.lease = None

    def save(self):
        if self.data is not None and self.dirty:
            self.store.save(self.data)
            self.dirty = False

    def begin_response(self, metadata, *, clear_draft=True):
        """Publish the pending turn before allowing inference to start.

        Roll back response insertion and draft clearing on publication failure.
        The caller may also roll back its newly appended user message. The edit
        remains dirty for retry; no transport or widgets are touched here.
        """
        snapshot = deepcopy(self.data)
        entry = message('assistant', status='streaming', request=metadata)
        self.data['messages'].append(entry)
        if clear_draft:
            self.data['draft'] = ''
            self.data['draft_images'] = []
        self.dirty = True
        try:
            self.save()
        except BaseException:
            self.data = snapshot
            self.dirty = True
            raise
        self.active_message = entry
        return entry

    def append_delta(self, text):
        if self.active_message is None:
            return False
        self.active_message['content'] += text
        self.dirty = True
        return True

    def complete_response(self, status, error, metadata):
        """Retain partial output and clear active ownership before publication."""
        if self.active_message is None:
            return False
        entry, self.active_message = self.active_message, None
        entry['status'] = status
        entry['response'] = metadata
        if error:
            entry['error'] = error
        self.dirty = True
        return True
