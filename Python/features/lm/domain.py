"""Versioned conversation records and bounded, stateless chat requests."""
from copy import deepcopy
from datetime import datetime, timezone
import math
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

STATUSES = {'complete', 'streaming', 'cancelled', 'interrupted', 'failed'}
MAX_TEXT = 2_000_000


def now():
    return datetime.now(timezone.utc).isoformat()


def identity(value):
    if not isinstance(value, str) or len(value) != 32 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Invalid LM record identity.')
    return value


def base_url(value):
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value):
        raise ValueError('Enter a server URL without control characters, under 4096 characters.')
    parts = urlsplit(value.strip())
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('Use an HTTP(S) API base URL without credentials, query or fragment.')
    try:
        parts.port
    except ValueError as error:
        raise ValueError('Invalid server port.') from error
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip('/'), '', ''))


def validate_settings(values):
    if not isinstance(values, dict):
        raise ValueError('Invalid generation settings.')
    result = {}
    for key, low, high in (('context_tokens', 256, 2_000_000), ('max_tokens', 1, 131072)):
        value = values.get(key)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'{key} must be between {low} and {high}.')
        result[key] = value
    if result['max_tokens'] >= result['context_tokens']:
        raise ValueError('Context size must exceed the maximum response tokens.')
    for key, high in (('temperature', 2), ('top_p', 1)):
        value = values.get(key)
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= high):
            raise ValueError(f'{key} must be a number between 0 and {high}, or server default.')
        result[key] = value
    value = values.get('system_prompt', '')
    if not isinstance(value, str) or len(value) > 65536:
        raise ValueError('System instructions must be text under 64 KiB characters.')
    result['system_prompt'] = value
    return result


def defaults():
    from pathlib import Path
    from commonUtils.configuration.settings import get_setting
    path = Path(__file__).with_name('config.ini')
    def read(key, fallback):
        return get_setting('Chat', key, fallback, path=path)
    values = dict(context_tokens=read('context_tokens_int', 8192), max_tokens=read('max_tokens_int', 1024),
                  temperature=read('temperature_float', -1.0), top_p=read('top_p_float', -1.0),
                  system_prompt=read('system_prompt_str', 'You are a helpful assistant.'))
    for key in ('temperature', 'top_p'):
        if values[key] < 0:
            values[key] = None
    try:
        return validate_settings(values)
    except ValueError:
        return dict(context_tokens=8192, max_tokens=1024, temperature=None, top_p=None,
                    system_prompt='You are a helpful assistant.')


def conversation(settings=None, profile_id='', model=''):
    return dict(schema_version=1, id=uuid4().hex, revision=0, title='New conversation', created=now(),
                updated=now(), profile_id=profile_id, model=model, draft='',
                settings=validate_settings(settings or defaults()), messages=[])


def message(role, content='', status='complete', **metadata):
    return dict(id=uuid4().hex, role=role, content=content, status=status, created=now(), **metadata)


def validate_conversation(data):
    if not isinstance(data, dict) or type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ValueError('Unsupported conversation format; original file preserved.')
    identity(data.get('id'))
    if type(data.get('revision')) is not int or data['revision'] < 0:
        raise ValueError('Invalid conversation revision.')
    for key in ('title', 'created', 'updated', 'profile_id', 'model', 'draft'):
        if not isinstance(data.get(key), str) or len(data[key]) > MAX_TEXT:
            raise ValueError(f'Invalid conversation {key}.')
    validate_settings(data.get('settings'))
    if not isinstance(data.get('messages'), list) or len(data['messages']) > 10000:
        raise ValueError('Invalid conversation messages.')
    seen = set()
    for entry in data['messages']:
        if not isinstance(entry, dict):
            raise ValueError('Invalid message record.')
        key = identity(entry.get('id'))
        if (key in seen or not isinstance(entry.get('role'), str) or entry['role'] not in ('user', 'assistant') or
                not isinstance(entry.get('status'), str) or entry['status'] not in STATUSES):
            raise ValueError('Invalid message identity, role or status.')
        seen.add(key)
        if not isinstance(entry.get('content'), str) or len(entry['content']) > MAX_TEXT:
            raise ValueError('Invalid message text.')
        if 'error' in entry and (not isinstance(entry['error'], str) or len(entry['error']) > MAX_TEXT):
            raise ValueError('Invalid message error details.')
    return data


def estimate_tokens(text):
    # UTF-8 heuristic, not a tokenizer. Server limits remain authoritative.
    return math.ceil(len(text.encode('utf-8')) / 3) + 8


def build_request(data):
    """Keep whole completed turns plus the latest user message; never split a turn."""
    settings = validate_settings(data['settings'])
    if not data['model'].strip():
        raise ValueError('Select or enter a model ID.')
    history = data['messages']
    users = [i for i, entry in enumerate(history) if entry['role'] == 'user']
    if not users:
        raise ValueError('Enter a message first.')
    latest = users[-1]
    current = {'role': 'user', 'content': history[latest]['content']}
    messages = []
    if settings['system_prompt']:
        messages.append({'role': 'system', 'content': settings['system_prompt']})
    budget = settings['context_tokens'] - settings['max_tokens']
    used = sum(estimate_tokens(m['content']) for m in [*messages, current]) + 32
    if used > budget:
        raise ValueError('The message and system instructions exceed the estimated context budget. Increase context or reduce the message/response limit.')
    groups = []
    for start, end in zip(users[:-1], users[1:]):
        turn = history[start:end]
        assistants = [m for m in turn if m['role'] == 'assistant' and m['status'] == 'complete']
        if assistants:
            groups.append(([{'role': 'user', 'content': turn[0]['content']},
                            {'role': 'assistant', 'content': assistants[-1]['content']}],
                           [turn[0]['id'], assistants[-1]['id']]))
    selected = []
    selected_ids = []
    for group, ids in reversed(groups):
        cost = sum(estimate_tokens(m['content']) for m in group)
        if used + cost > budget:
            break
        used += cost
        selected[0:0] = group
        selected_ids[0:0] = ids
    messages.extend(selected)
    messages.append(current)
    payload = dict(model=data['model'], messages=messages, stream=True, max_tokens=settings['max_tokens'])
    for key in ('temperature', 'top_p'):
        if settings[key] is not None:
            payload[key] = settings[key]
    metadata = dict(settings=deepcopy(settings), model=data['model'], profile_id=data['profile_id'],
                    message_ids=[*selected_ids, history[latest]['id']], estimated_input_tokens=used,
                    omitted_turns=len(users) - 1 - len(selected) // 2)
    return payload, metadata
