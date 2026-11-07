"""Read verified legacy video state for import into the shared store."""

from hashlib import sha256
import json
from math import isfinite


def legacy_record(progress):
    content = progress.content
    if progress.private:
        if progress.state.mode != 'encrypted':
            return {}
        if progress.remote:
            from .video_state import RemoteProgress

            legacy = RemoteProgress(content, progress.root, progress.remote_cipher)
            position = legacy.load()
            if position or legacy.settings is not None or legacy.duration:
                from dataclasses import asdict

                return dict(position=position, duration=legacy.duration,
                            settings=asdict(legacy.settings) if legacy.settings else {})
            return {}

    identity = [content.provider.storage_id, getattr(content.provider, 'storage_namespace', ''), content.path]
    path_key = sha256(json.dumps(identity).encode()).hexdigest()
    candidates = [(path_key, content.source.expected)]
    if progress.fingerprint:
        candidates.insert(0, (progress.fingerprint, progress.fingerprint))
    for key, revision in candidates:
        try:
            raw = _read(progress, key + '.json')
        except FileNotFoundError:
            continue
        if len(raw) > 4096:
            continue
        record = json.loads(raw)
        if not isinstance(record, dict) or record.get('schema') != 1 or record.get('generation', ''):
            continue
        position = record.get('position')
        if (record.get('revision') != json.dumps(revision, sort_keys=True)
                or type(position) not in (int, float) or not isfinite(position) or not 0 <= position <= 10**10):
            continue
        return dict(position=int(position), duration=progress.valid_duration(record.get('duration')),
                    settings=record.get('settings', {}))
    return {}


def _read(progress, filename):
    if progress.private:
        from commonUtils.runtime.resources.content import ProviderContent

        path = '.logistics-video/' + filename
        source = ProviderContent(progress.content.provider, path)
        try:
            with source.open(path) as stream:
                return stream.read(4097)
        finally:
            source.close()
    path = progress.root / filename
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Linked legacy video progress was preserved.')
    with path.open('rb') as stream:
        return stream.read(4097)


def legacy_protected_path_record(progress):
    """Recognize only the verified pre-fingerprint ZIP envelope at this key."""
    from .credential_state import CredentialState, position_generation

    if position_generation(progress.root.parent):
        return {}
    content = progress.content
    legacy = CredentialState(content.provider, content.path, progress.root.parent,
                             kind='video', revision=content.source.expected,
                             app=progress.app, check=progress._check)
    try:
        record = legacy.read_checkpoint(legacy.binding())
    except FileNotFoundError:
        return {}
    if (record.get('version') == 1 and record.get('revision') == legacy.revision
            and isinstance(record.get('state'), dict)):
        return record['state']
    return {}
