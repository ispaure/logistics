"""Host video resume storage; private records are encrypted by their provider."""
from hashlib import sha256
from io import BytesIO
import json
from math import isfinite
from pathlib import Path

from services.documents.storage import DocumentPolicy, document_writable, document_remote


class VideoProgress:
    def __init__(self, content, root):
        self.content, self.root = content, Path(root)
        self.private = not DocumentPolicy.for_provider(content.provider).persistent
        self.memory = {}
        self.remote = document_remote(content.provider)
        if self.remote:
            return
        self.revision = json.dumps(content.source.expected, sort_keys=True)
        identity = [content.provider.storage_id, getattr(content.provider, 'storage_namespace', ''), content.path]
        self.key = sha256(json.dumps(identity).encode()).hexdigest() + '.json'
        # In LocalCrypt this folder, filename AND payload pass through the
        # provider's encryption. No private identity is written into app state.
        self.path = '.logistics-video/' + self.key
        self.memory = {}

    def load(self):
        self.content.check_access() if self.remote else self.content.check()
        if self.remote:
            return self.memory.get('position', 0)
        try:
            if self.private:
                from commonUtils.runtime.resources.content import ProviderContent
                source = ProviderContent(self.content.provider, self.path)
                try:
                    with source.open(self.path) as stream:
                        raw = stream.read(4097)
                finally:
                    source.close()
            else:
                path = self.root / self.key
                if path.is_symlink():
                    raise ValueError('Linked video resume state is not supported.')
                with path.open('rb') as stream:
                    raw = stream.read(4097)
            if len(raw) > 4096:
                return 0
            record = json.loads(raw)
            position = record.get('position', 0)
            if (record.get('schema') == 1 and record.get('revision') == self.revision and type(position) in (int, float)
                    and isfinite(position) and 0 <= position <= 10**10):
                return int(position)
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        return 0

    def save(self, milliseconds, *, completed=False):
        self.content.check_access() if self.remote else self.content.check()
        if type(milliseconds) not in (int, float) or not isfinite(milliseconds) or milliseconds < 0:
            raise ValueError('Invalid video position.')
        position = 0 if completed else int(milliseconds)
        if self.remote:
            self.memory = dict(position=position)
            return
        record = dict(schema=1, revision=self.revision, position=position)
        self.memory = record
        if self.private:
            provider = self.content.provider
            if not document_writable(provider):
                raise PermissionError('Resume is available only for this session on read-only storage.')
            try:
                provider.mkdir('.logistics-video')
            except FileExistsError:
                pass
            raw = json.dumps(record).encode()
            try:
                revision = provider.entry(self.path)['revision']
            except FileNotFoundError:
                provider.create_file(self.path, BytesIO(raw))
            else:
                if hasattr(provider, 'replace_bytes'):
                    provider.replace_bytes(self.path, raw, expected_revision=revision)
                else:
                    provider.replace_stream(self.path, lambda stream: stream.write(raw), expected_revision=revision)
        else:
            from commonUtils.persistence import atomic_write_json
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_write_json(self.root / self.key, record, max_bytes=4096)
