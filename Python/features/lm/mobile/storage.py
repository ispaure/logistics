"""Mobile conversation persistence using the desktop LM domain contracts."""
from copy import deepcopy
import json
from pathlib import Path

from commonUtils.persistence import atomic_write_bytes
from features.lm.domain import (base_url, conversation, identity, now, validate_conversation,
                                validate_settings)

MAX_RECORD = 2 * 1024 * 1024
DEFAULT_SETTINGS = dict(context_tokens=8192, max_tokens=1024, temperature=None, top_p=None,
                        system_prompt='You are a helpful assistant.')


class ChatStore:
    def __init__(self, root):
        root = Path(root)
        if not root.is_absolute():
            raise ValueError('Chat storage requires an absolute private directory.')
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, key):
        path = self.root / (identity(key) + '.json')
        if path.is_symlink():
            raise ValueError('Conversation files cannot be symbolic links.')
        return path

    @staticmethod
    def validate(data):
        validate_conversation(data)
        if (data.get('mode', 'chat') != 'chat' or data.get('draft_images')
                or len(data['messages']) > 200 or any(m.get('images') for m in data['messages'])):
            raise ValueError('Mobile chat supports up to 200 text-only messages; original was preserved.')
        if len(data['draft']) > 65536:
            raise ValueError('Mobile drafts are limited to 64 KiB characters.')
        return data

    def _bytes(self, path):
        if path.is_symlink():
            raise ValueError('Conversation files cannot be symbolic links.')
        with path.open('rb') as stream:
            data = stream.read(MAX_RECORD + 1)
        if len(data) > MAX_RECORD:
            raise ValueError('Mobile chat files are limited to 2 MiB; original was preserved.')
        return data

    def load(self, key):
        data = self.validate(json.loads(self._bytes(self.path(key))))
        if data['id'] != key:
            raise ValueError('Conversation identity mismatch; original was preserved.')
        for entry in data['messages']:
            if entry['status'] == 'streaming':
                entry['status'] = 'interrupted'
        return data

    def items(self):
        records, warnings = [], []
        for path in sorted(self.root.glob('*.json')):
            if path.name == 'profile.json':
                continue
            try:
                records.append(self.load(path.stem))
            except (OSError, ValueError, KeyError, TypeError) as error:
                warnings.append(str(error))
        return sorted(records, key=lambda d: d['updated'], reverse=True), warnings

    def new(self, settings=None):
        data = conversation(settings or DEFAULT_SETTINGS, profile_id='mobile')
        self.save(data)
        return data

    def save(self, data):
        self.validate(data)
        path = self.path(data['id'])
        original = self._bytes(path) if path.exists() else None
        if original is not None:
            current = self.validate(json.loads(original))
            if current['id'] != data['id'] or current['revision'] != data['revision']:
                raise OSError('Conversation changed on disk; export the current copy before reopening.')
        elif data['revision'] != 0:
            raise OSError('Conversation disappeared; export the current copy before reopening.')
        saved = deepcopy(data)
        saved.update(revision=data['revision'] + 1, updated=now())
        encoded = json.dumps(saved, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(encoded) > MAX_RECORD:
            raise ValueError('Mobile chat files are limited to 2 MiB.')
        def check():
            current = self._bytes(path) if path.exists() else None
            if current != original:
                raise OSError('Conversation changed while saving; current copy was preserved.')
        atomic_write_bytes(path, encoded, validate=check)
        data.update(revision=saved['revision'], updated=saved['updated'])

    def profile(self):
        path = self.root / 'profile.json'
        if path.is_symlink():
            raise ValueError('Chat profiles cannot be symbolic links.')
        if not path.exists():
            return dict(schema=1, base_url='', model='', settings=dict(DEFAULT_SETTINGS)), None
        original = self._bytes(path)
        return self.validate_profile(json.loads(original)), original

    @staticmethod
    def validate_profile(data):
        if (not isinstance(data, dict) or data.get('schema') != 1
                or set(data) != {'schema', 'base_url', 'model', 'settings'}
                or not isinstance(data['base_url'], str) or not isinstance(data['model'], str)
                or len(data['model']) > 200 or any(ord(c) < 32 for c in data['model'])):
            raise ValueError('Invalid mobile chat profile; original was preserved.')
        url = base_url(data['base_url']) if data['base_url'] else ''
        return dict(schema=1, base_url=url, model=data['model'], settings=validate_settings(data['settings']))

    def save_profile(self, data, original):
        data = self.validate_profile(data)
        path = self.root / 'profile.json'
        def check():
            if path.is_symlink():
                raise ValueError('Chat profiles cannot be symbolic links.')
            current = self._bytes(path) if path.exists() else None
            if current != original:
                raise OSError('Chat profile changed; reload before saving.')
        encoded = json.dumps(data, ensure_ascii=False).encode('utf-8')
        atomic_write_bytes(path, encoded, validate=check)
        return data, encoded


def export_chat(data):
    ChatStore.validate(data)
    sections = [f'# {data["title"]}']
    for entry in data['messages']:
        status = '' if entry['status'] == 'complete' else ' (' + entry['status'] + ')'
        sections.append(f'## {entry["role"].title()}{status}\n\n{entry["content"]}')
    return '\n\n'.join(sections) + '\n'
