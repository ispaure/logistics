"""Validated, ordered offline canvas commands; no content navigation is allowed."""
import json
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4

MAX_COMMAND = 8 * 1024 * 1024

class RetiredCanvas(Exception):
    """An awaited operation completed after its originating surface retired."""


class Bridge:
    def __init__(self):
        self.url = 'logistics-notebook://' + uuid4().hex + '/'
        self.sequence = 0
        self.active = True

    def retire(self):
        self.active = False

    async def wait(self, operation):
        result = await operation
        if not self.active:
            raise RetiredCanvas()
        return result

    def command(self, url):
        if not self.active or len(url) > MAX_COMMAND or url.split('?', 1)[0] != self.url:
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
