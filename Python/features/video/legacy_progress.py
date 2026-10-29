"""Retire pre-password-policy video checkpoints when their source is unlocked."""

from hashlib import sha256
import json
from pathlib import Path


def retire_legacy(content, root, state, *, cleared=False, remote_cipher=None):
    if content.remote:
        from .secure_state import RemoteProgress

        path = RemoteProgress(content, root, remote_cipher).path
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("Linked legacy video state was preserved.")
        path.unlink(missing_ok=True)
        return
    identity = [
        content.provider.storage_id,
        getattr(content.provider, "storage_namespace", ""),
        content.path,
    ]
    key = sha256(json.dumps(identity).encode()).hexdigest() + ".json"
    path = ".logistics-video/" + key
    provider = content.provider
    try:
        provider.entry(path)
    except FileNotFoundError:
        return
    # Never restore storage-key-only metadata after Clear, or without the ZIP key.
    if not cleared:
        try:
            state.cipher.identity
        except PermissionError:
            pass
        else:
            from commonUtils.runtime.resources.content import ProviderContent

            source = ProviderContent(provider, path)
            try:
                with source.open(path) as stream:
                    raw = stream.read(4097)
                if len(raw) <= 4096:
                    record = json.loads(raw)
                    if not isinstance(record, dict):
                        raise ValueError("Invalid old checkpoint was preserved.")
                    position = record.get("position", 0)
                    if (
                        record.get("schema") == 1
                        and record.get("revision")
                        == json.dumps(content.source.expected, sort_keys=True)
                        and type(position) is int
                        and 0 <= position <= 10**10
                    ):
                        if not state.load():
                            state.save(dict(position=position))
                            if state.load().get("position") != position:
                                raise ValueError(
                                    "Legacy resume migration could not be verified."
                                )
            finally:
                source.close()
    from commonUtils.runtime.resources.mutations import delete_resource

    delete_resource(provider, path)
