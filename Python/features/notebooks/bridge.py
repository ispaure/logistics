"""Validated, ordered offline canvas commands; no content navigation is allowed."""
import json
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4


class Bridge:
    def __init__(self):
        self.url = 'logistics-notebook://' + uuid4().hex + '/'
        self.sequence = 0

    def command(self, url):
        if len(url) > 8 * 1024 * 1024 or url.split('?', 1)[0] != self.url:
            return None
        try:
            values = parse_qs(urlsplit(url).query, strict_parsing=True)
            if set(values) != {'command'} or len(values['command']) != 1:
                return None
            payload = json.loads(values['command'][0])
            sequence, action = payload['sequence'], payload['action']
            if type(sequence) is not int or sequence != self.sequence + 1 or not isinstance(action, dict):
                return None
            if not isinstance(action.get('op'), str):
                return None
            self.sequence = sequence
            return action
        except (ValueError, KeyError, TypeError):
            return None


def update_script(state, error=''):
    return 'window.notebookUpdate(' + json.dumps(state, allow_nan=False) + ',' + json.dumps(error) + ')'
