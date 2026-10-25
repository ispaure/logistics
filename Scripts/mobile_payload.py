"""Refresh a manager snapshot's generated payload with owned scratch rollback."""
from pathlib import Path
from Scripts.build_retention import scratch


def stage_payload(root, interpreter, command):
    root = Path(root)
    if not (root / '.manager-source.json').is_file():
        raise ValueError('Payload refresh requires a manager-owned source snapshot.')
    mobile = root / 'mobile_build'
    payload = mobile / 'payload'
    if payload.is_symlink():
        raise ValueError('Refusing a linked mobile payload.')
    with scratch(root) as temporary:
        previous = temporary / 'previous-payload'
        if payload.exists():
            payload.rename(previous)
        try:
            command([interpreter, 'tools.py', 'stage', 'payload', '--repo', str(root), '--allow-dirty'], mobile)
        except BaseException:
            if payload.exists():
                payload.rename(temporary / 'failed-payload')
            if previous.exists():
                previous.rename(payload)
            raise
