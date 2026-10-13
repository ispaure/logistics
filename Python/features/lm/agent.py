"""Read-only agent orchestration with asynchronous, cooperatively cancelled tools."""
from copy import deepcopy
import json
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operations import ResultWorker
from .domain import estimate_tokens, message_tokens, MAX_TEXT
from .transport import Client


class AgentClient(qt.QObject):
    delta = qt.Signal(str)
    models = qt.Signal(list)
    completed = qt.Signal(str, str, object)
    activity = qt.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.http = Client(self)
        self.http.delta.connect(self._delta)
        self.http.models.connect(self.models.emit)
        self.http.completed.connect(self._completed)
        self.worker = None
        self.active = False
        self.stopped = False
        self.tools = None
        self.steps = []
        self.round_text = ''
        self.total_text = 0
        self.overflow = False

    @property
    def busy(self):
        return self.active or self.http.busy or self.worker is not None

    @property
    def timeout_ms(self):
        return self.http.timeout_ms

    @timeout_ms.setter
    def timeout_ms(self, value):
        self.http.timeout_ms = value

    def start(self, profile, token='', payload=None, *, project_tools=None, context_tokens=8192):
        if self.busy:
            raise ValueError('An LM request is already running.')
        self.tools = project_tools
        self.payload = deepcopy(payload)
        self.profile = dict(profile)
        self.token = token
        self.context_tokens = context_tokens
        self.steps = []
        self.round_text = ''
        self.total_text = 0
        self.overflow = False
        self.stopped = False
        self.rounds = 0
        if project_tools:
            self._check_budget()
        self.http.start(profile, token, payload)
        self.active = True

    def _check_budget(self):
        size = sum(message_tokens(entry) + 16 for entry in self.payload['messages'])
        size += estimate_tokens(json.dumps(self.payload.get('tools', []))) + 32
        if size + self.payload['max_tokens'] > self.context_tokens:
            raise ValueError('Project context reached the estimated model context limit. Increase context size or start a shorter conversation.')

    def cancel(self):
        self.stopped = True
        if self.worker:
            self.worker.cancel()
        self.http.cancel()

    def _delta(self, text):
        if self.total_text + len(text) > MAX_TEXT:
            self.overflow = True
            self.http.failure = 'Response exceeds the text size limit.'
            if self.http.reply is not None:
                self.http.reply.abort()
            return
        self.total_text += len(text)
        self.round_text += text
        self.delta.emit(text)

    def _finish(self, status, error, metadata):
        if self.steps:
            metadata = dict(metadata, tool_steps=self.steps)
        self.active = False
        self.tools = None
        self.token = ''
        self.payload = None
        self.completed.emit(status, error, metadata)

    def _completed(self, status, error, metadata):
        calls = metadata.get('tool_calls') or []
        if self.overflow:
            self._finish('failed', 'Response exceeds the text size limit.', metadata)
        elif self.stopped:
            self._finish('cancelled', '', metadata)
        elif status != 'complete' or not calls or not self.tools:
            self._finish(status, error, metadata)
        else:
            try:
                if self.rounds >= 6 or len(self.steps) + len(calls) > 24:
                    raise ValueError('Project tool limit reached. Ask a narrower question to continue.')
                if not isinstance(calls, list) or not 1 <= len(calls) <= 8:
                    raise ValueError('Invalid model tool calls.')
                seen = set()
                for call in calls:
                    key, function = call['id'], call['function']
                    if (not isinstance(key, str) or not key or len(key) > 200 or key in seen
                            or call.get('type') != 'function'
                            or not isinstance(function['name'], str) or len(function['name']) > 100
                            or not isinstance(function['arguments'], str) or len(function['arguments']) > 65536):
                        raise ValueError('Invalid model tool call.')
                    seen.add(key)
                self.rounds += 1
                self.payload['messages'].append(dict(role='assistant', content=self.round_text or None, tool_calls=calls))
                if self.round_text:
                    self._delta('\n\n')
                self.round_text = ''
                self.activity.emit('Reading project… ' + ', '.join(
                    call['function']['name'] + ' ' + call['function']['arguments'][:160] for call in calls))
                tools = self.tools
                def execute():
                    results = []
                    for call in calls:
                        if self.stopped or worker.isInterruptionRequested():
                            break
                        function = call['function']
                        results.append(tools.execute(function['name'], function['arguments'],
                            cancelled=lambda: self.stopped or worker.isInterruptionRequested()))
                    return results
                worker = self.worker = ResultWorker(execute, self)
                def finished():
                    self.worker = None
                    try:
                        if self.stopped:
                            self._finish('cancelled', '', {})
                            return
                        if worker.error:
                            raise ValueError('Project files could not be read.')
                        for call, result in zip(calls, worker.result):
                            self.payload['messages'].append(dict(role='tool', tool_call_id=call['id'], content=result))
                            self.steps.append(dict(name=call['function']['name'], arguments=call['function']['arguments'], result=result))
                        self._check_budget()
                        self.activity.emit('Generating from project context…')
                        self.http.start(self.profile, self.token, self.payload)
                    except (ValueError, OSError) as error:
                        self._finish('failed', str(error), {})
                    finally:
                        worker.deleteLater()
                worker.finished.connect(finished)
                worker.start()
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                self._finish('failed', str(error) if isinstance(error, ValueError) else 'Invalid model tool calls.', {})
