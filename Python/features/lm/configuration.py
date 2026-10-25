"""Validate centrally edited chat defaults before publication."""
from .domain import validate_settings


def response_notifications_enabled():
    from pathlib import Path
    from commonUtils.configuration.settings import get_setting
    return get_setting('Chat', 'response_notifications_bool', True,
                       path=Path(__file__).with_name('config.ini'))


def validate(values):
    def read(section, key, default, cast):
        return cast(values.get((section, key), default))
    temperature = read('Chat', 'temperature_float', -1, float)
    top_p = read('Chat', 'top_p_float', -1, float)
    for name, value in (('temperature', temperature), ('top_p', top_p)):
        if value < 0 and value != -1:
            raise ValueError(f'{name}: use -1 for server default, or a nonnegative value.')
    validate_settings(dict(context_tokens=read('Chat', 'context_tokens_int', 8192, int),
                           max_tokens=read('Chat', 'max_tokens_int', 1024, int),
                           temperature=None if temperature == -1 else temperature,
                           top_p=None if top_p == -1 else top_p,
                           system_prompt=read('Chat', 'system_prompt_str', 'You are a helpful assistant.', str)))
    if not 5 <= read('Connection', 'timeout_seconds_int', 180, int) <= 3600:
        raise ValueError('Inactivity timeout must be between 5 and 3600 seconds.')
