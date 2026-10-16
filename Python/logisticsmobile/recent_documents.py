"""Six ordinary document identities; private provider sessions never enter history."""
import json
from commonUtils.persistence import atomic_write_json
from .workspace import Session, uuid, KINDS, PROVIDERS


class RecentDocuments:
    def __init__(self, root):
        self.path = root / 'recent-documents.json'
        self.items = []
        self.error = ''
        try:
            if self.path.is_symlink():
                raise ValueError('Recent documents cannot be linked.')
            if self.path.exists():
                if self.path.stat().st_size > 4096:
                    raise ValueError('Recent document history is too large.')
                items = json.loads(self.path.read_text())
                if not isinstance(items, list) or len(items) > 6:
                    raise ValueError('Invalid recent document history.')
                for item in items:
                    if (not isinstance(item, dict) or set(item) != {'provider', 'resource', 'kind'}
                            or item['provider'] not in PROVIDERS or not uuid(item['resource'])
                            or item['kind'] not in KINDS):
                        raise ValueError('Invalid recent document identity.')
                self.items = items
        except (OSError, ValueError, TypeError) as error:
            self.error = str(error)

    def remember(self, session):
        if session is None or self.error:
            return
        items = [item for item in self.items
                 if (item['provider'], item['resource']) != session.identity]
        if not session.transient and session.provider in PROVIDERS:
            items.insert(0, dict(provider=session.provider, resource=session.resource, kind=session.kind))
        items = items[:6]
        if items != self.items:
            atomic_write_json(self.path, items, max_bytes=4096, durable_directory=True)
            self.items = items

    def sessions(self):
        return [Session(id='', **item) for item in self.items]

    def forget(self, provider, resource):
        if self.error:
            raise ValueError('Recent history could not be read; it was preserved.')
        items = [item for item in self.items
                 if (item['provider'], item['resource']) != (provider, resource)]
        if items != self.items:
            atomic_write_json(self.path, items, max_bytes=4096, durable_directory=True)
            self.items = items
