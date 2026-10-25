"""Non-secret profile values and explicit precedence; providers own credentials."""
import json
import os
from pathlib import Path


def effective(defaults, profile=None, environment=None, overrides=None, *, variables=None):
    values = dict(defaults)
    sources = dict.fromkeys(values, 'repository default')
    for origin, incoming in [('local profile', profile or {}), ('environment',
            {key: environment[name] for key, name in (variables or {}).items()
             if environment is not None and name in environment}), ('run override', overrides or {})]:
        for name, value in incoming.items():
            if name not in defaults:
                raise ValueError('Unsupported setting: ' + name)
            values[name], sources[name] = value, origin
    return values, sources


def save_profile(path, values, *, allowed):
    if set(values) - set(allowed):
        raise ValueError('Unsupported profile fields.')
    encoded = json.dumps(dict(schema=1, values=values), indent=2) + '\n'
    if '-----BEGIN ' in encoded or any(name.lower() in {'password', 'token', 'private_key'} for name in values):
        raise ValueError('Profiles store credential references, never secret contents.')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix('.tmp')
    # Existing files must also receive restrictive permissions.
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != 'nt':
            temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_profile(path):
    path = Path(path)
    if not path.exists():
        return {}
    result = json.loads(path.read_text())
    if result.get('schema') != 1 or not isinstance(result.get('values'), dict):
        raise ValueError('Unsupported profile schema.')
    return result['values']
