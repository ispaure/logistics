"""Reusable Logistics localcrypt fixtures; no test cases or discovery side effects."""


def seed_offline_copy(copies, data=b'opaque-original'):
    """Seed a pre-existing offline record without a remote download API."""
    import json
    from uuid import uuid4
    key = uuid4().hex
    folder = copies.root / key
    folder.mkdir()
    (folder / 'data').write_bytes(data)
    (folder / 'record.json').write_text(json.dumps(dict(
        remote='Secret', encrypted_path='encoded', identity='a' * 64)))
    return key
