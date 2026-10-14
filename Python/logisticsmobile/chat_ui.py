"""Native text chat controls; only explicit user actions contact a server."""
import asyncio
from copy import deepcopy
import time
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from features.lm.domain import build_request, message, validate_settings
from .chat import ChatStore, DEFAULT_SETTINGS, export_chat
from .chat_transport import ChatClient, ChatCancelled


class ChatUI:
    def show_chat(self, widget=None, **kwargs):
        if not hasattr(self, 'chat_store'):
            self.chat_store = ChatStore(self.private_root / 'LM')
            self.chat_current = None
            self.chat_busy = self.chat_loading = False
            self.chat_client = None
            self.chat_labels = {}
            try:
                self.chat_profile, self.chat_profile_original = self.chat_store.profile()
                error = ''
            except (OSError, ValueError) as problem:
                self.chat_profile = dict(schema=1, base_url='', model='', settings=dict(DEFAULT_SETTINGS))
                self.chat_profile_original = None
                error = str(problem)
            self.chat_url = toga.TextInput(value=self.chat_profile['base_url'],
                placeholder='Server API URL, e.g. https://host/v1', style=Pack(height=44))
            self.chat_key = toga.PasswordInput(placeholder='API key (session only)', style=Pack(height=44))
            self.chat_model = toga.TextInput(value=self.chat_profile['model'], placeholder='Model ID', style=Pack(height=44))
            self.chat_models = toga.Selection(on_change=self.select_chat_model, style=Pack(height=44))
            self.chat_refresh = toga.Button('Refresh models', on_press=self.refresh_chat_models, style=Pack(height=44))
            self.chat_selector = toga.Selection(on_change=self.select_chat, style=Pack(height=44))
            self.chat_new = toga.Button('New conversation', on_press=self.new_chat, style=Pack(height=44))
            self.chat_transcript = toga.MultilineTextInput(readonly=True, style=Pack(flex=1,
                font_size=int(self.preferences.values['font_size'])))
            self.chat_prompt = toga.MultilineTextInput(on_change=self.chat_draft_changed,
                placeholder='Message', style=Pack(height=100, font_size=int(self.preferences.values['font_size'])))
            self.chat_send = toga.Button('Send', on_press=self.send_chat, style=Pack(flex=1, height=44))
            self.chat_cancel = toga.Button('Cancel', on_press=self.cancel_chat, enabled=False, style=Pack(flex=1, height=44))
            self.chat_export = toga.Button('Export conversation…', on_press=self.export_chat, style=Pack(height=44))
            contexts = sorted({'2048', '4096', '8192', '16384', '32768', str(self.chat_profile['settings']['context_tokens'])}, key=int)
            replies = sorted({'256', '512', '1024', '2048', '4096', str(self.chat_profile['settings']['max_tokens'])}, key=int)
            self.chat_context = toga.Selection(items=contexts,
                value=str(self.chat_profile['settings']['context_tokens']), style=Pack(flex=1, height=44))
            self.chat_max_tokens = toga.Selection(items=replies,
                value=str(self.chat_profile['settings']['max_tokens']), style=Pack(flex=1, height=44))
            self.chat_status = toga.MultilineTextInput(value=error or 'Configure a server; no connection starts automatically.',
                                                      readonly=True, style=Pack(height=50, font_size=12))
            self.chat_config_view = toga.Box(children=[
                toga.Button('Back to conversation', on_press=self.show_chat, style=Pack(height=44)),
                toga.Label('Server & generation settings'), self.chat_url, self.chat_key, self.chat_model,
                toga.Label('Context tokens / maximum\nreply tokens'),
                toga.Box(children=[self.chat_context, self.chat_max_tokens], style=Pack(direction=ROW)),
                self.chat_refresh, self.chat_models,
                toga.Button('Save configuration', on_press=self.save_chat_configuration, style=Pack(height=44))],
                style=Pack(direction=COLUMN, margin=12))
            self.chat_view = toga.Box(children=[
                toga.Button('All documents', on_press=self.show_documents_hub, style=Pack(height=44)),
                toga.Button('Server & generation settings…', on_press=self.show_chat_configuration, style=Pack(height=44)),
                self.chat_selector, self.chat_new, self.chat_transcript,
                self.chat_prompt, toga.Box(children=[self.chat_send, self.chat_cancel], style=Pack(direction=ROW)),
                self.chat_export, self.chat_status], style=Pack(direction=COLUMN, margin=12, flex=1))
            self.refresh_chats()
            if self.chat_labels:
                self.open_chat(next(iter(self.chat_labels.values())))
            else:
                self.new_chat()
        self.show_view(self.chat_view, destination='documents', route='chat', title='LM Chat')

    def show_chat_configuration(self, widget=None, **kwargs):
        self.show_view(self.chat_config_view, destination='documents')

    def save_chat_configuration(self, widget=None, **kwargs):
        if self.chat_busy:
            return
        try:
            self.chat_fields()
            self.chat_status.value = 'Configuration saved. The API key stays in this session only.'
            self.show_chat()
        except (OSError, ValueError) as error:
            self.chat_status.value = str(error)
            self.show_chat()

    def refresh_chats(self):
        records, warnings = self.chat_store.items()
        self.chat_loading = True
        labels = {}
        for record in records:
            label = record['title'][:60]
            while label in labels:
                label += ' (copy)'
            labels[label] = record['id']
        self.chat_labels = labels
        self.chat_selector.items = list(labels)
        if self.chat_current:
            self.chat_selector.value = next((label for label, key in labels.items() if key == self.chat_current['id']), None)
        self.chat_loading = False
        if warnings:
            self.chat_status.value = f'{len(warnings)} conversation(s) could not be read; originals preserved.'

    def checkpoint_chat(self):
        if self.chat_current is None:
            return True
        try:
            self.chat_store.save(self.chat_current)
            return True
        except (OSError, ValueError) as error:
            self.chat_status.value = 'Chat not saved: ' + str(error)
            return False

    def open_chat(self, key):
        if self.chat_busy or not self.checkpoint_chat():
            return
        try:
            self.chat_current = self.chat_store.load(key)
            self.chat_loading = True
            self.chat_prompt.value = self.chat_current['draft']
            self.chat_loading = False
            self.update_chat_transcript()
            self.refresh_chats()
        except (OSError, ValueError) as error:
            self.chat_status.value = str(error)

    def select_chat(self, widget, **kwargs):
        if not self.chat_loading and not self.chat_busy and widget.value in self.chat_labels:
            self.open_chat(self.chat_labels[widget.value])

    def new_chat(self, widget=None, **kwargs):
        if self.chat_busy or not self.checkpoint_chat():
            return
        try:
            self.chat_current = self.chat_store.new(self.chat_profile['settings'])
            self.chat_loading = True
            self.chat_prompt.value = ''
            self.chat_loading = False
            self.update_chat_transcript()
            self.refresh_chats()
        except (OSError, ValueError) as error:
            self.chat_status.value = str(error)

    def chat_draft_changed(self, widget, **kwargs):
        if not self.chat_loading and self.chat_current is not None:
            self.chat_current['draft'] = widget.value
            self.checkpoint_chat()

    def update_chat_transcript(self):
        self.chat_transcript.value = '\n\n'.join(
            entry['role'].title() + (' (' + entry['status'] + ')' if entry['status'] != 'complete' else '')
            + '\n' + entry['content'] for entry in self.chat_current['messages'])

    def set_chat_busy(self, busy):
        self.chat_busy = busy
        for control in (self.chat_url, self.chat_key, self.chat_model, self.chat_models, self.chat_selector,
                        self.chat_new, self.chat_refresh, self.chat_send, self.chat_export,
                        self.chat_context, self.chat_max_tokens):
            control.enabled = not busy
        self.chat_cancel.enabled = busy

    def chat_fields(self):
        settings = dict(self.chat_profile['settings'], context_tokens=int(self.chat_context.value),
                        max_tokens=int(self.chat_max_tokens.value))
        validate_settings(settings)
        profile = dict(schema=1, base_url=self.chat_url.value.strip(), model=self.chat_model.value.strip(), settings=settings)
        self.chat_profile, self.chat_profile_original = self.chat_store.save_profile(profile, self.chat_profile_original)
        return profile

    def select_chat_model(self, widget, **kwargs):
        if not self.chat_loading and widget.value:
            self.chat_model.value = widget.value

    async def refresh_chat_models(self, widget=None, **kwargs):
        if self.chat_busy:
            return
        self.set_chat_busy(True)
        try:
            profile = self.chat_fields()
            self.chat_client = ChatClient(profile['base_url'], self.chat_key.value)
            models = await asyncio.to_thread(self.chat_client.models)
            self.chat_models.items = models
            if models:
                self.chat_model.value = self.chat_profile['model'] if self.chat_profile['model'] in models else models[0]
            self.chat_status.value = f'{len(models)} model(s) available.' if models else 'No models are loaded on the server.'
        except Exception as error:
            self.chat_status.value = 'Models unavailable: ' + str(error)[:400]
        finally:
            self.chat_client = None
            self.set_chat_busy(False)

    async def send_chat(self, widget=None, **kwargs):
        if self.chat_busy or self.chat_current is None:
            return
        prompt = self.chat_prompt.value.strip()
        if not prompt:
            self.chat_status.value = 'Enter a message first.'
            return
        if len(self.chat_current['messages']) > 198:
            self.chat_status.value = 'This conversation has reached 200 messages. Start a new conversation.'
            return
        self.set_chat_busy(True)
        self.chat_cancelled = False
        assistant = None
        pending = []
        loop = asyncio.get_running_loop()
        try:
            profile = self.chat_fields()
            data = self.chat_current
            before = deepcopy(data)
            data['settings'], data['model'] = profile['settings'], profile['model']
            data['messages'].append(message('user', prompt))
            try:
                payload, metadata = build_request(data)
                self.chat_client = ChatClient(profile['base_url'], self.chat_key.value)
            except Exception:
                data['messages'].pop()
                raise
            metadata['base_url'] = profile['base_url']
            assistant = message('assistant', status='streaming', request=metadata)
            data['messages'].append(assistant)
            data['title'] = next(m['content'].splitlines()[0][:60] for m in data['messages'] if m['role'] == 'user')
            data['draft'] = ''
            self.chat_loading = True
            self.chat_prompt.value = ''
            self.chat_loading = False
            if not self.checkpoint_chat():
                data.clear()
                data.update(before)
                assistant = None
                self.chat_loading = True
                self.chat_prompt.value = data['draft']
                self.chat_loading = False
                raise ValueError('The request was not sent because its recovery record could not be saved.')
            self.update_chat_transcript()
            omitted = metadata['omitted_turns']
            self.chat_status.value = f'Generating… {omitted} older turn(s) omitted from the estimated context budget.'
            def fragment(text):
                loop.call_soon_threadsafe(pending.append, text)
            task = asyncio.create_task(asyncio.to_thread(self.chat_client.stream, payload, fragment))
            saved_at = time.monotonic()
            while not task.done() or pending:
                if pending:
                    assistant['content'] += ''.join(pending)
                    pending.clear()
                    self.update_chat_transcript()
                    if time.monotonic() - saved_at > .5:
                        if not self.checkpoint_chat():
                            self.chat_client.cancel()
                        saved_at = time.monotonic()
                await asyncio.sleep(.05)
            reason = await task
            assistant['status'] = 'cancelled' if self.chat_cancelled else 'complete'
            assistant['finish_reason'] = reason
            self.chat_status.value = 'Reply cancelled; partial text preserved.' if self.chat_cancelled else 'Reply complete.'
        except ChatCancelled:
            if assistant:
                assistant['status'] = 'cancelled'
            self.chat_status.value = 'Request cancelled; partial text preserved.'
        except asyncio.CancelledError:
            if assistant:
                assistant['status'] = 'interrupted'
            raise
        except Exception as error:
            if assistant:
                assistant['status'] = 'failed'
                assistant['error'] = str(error)[:400]
            self.chat_status.value = 'Chat failed: ' + str(error)[:400]
        finally:
            self.chat_loading = False
            if self.chat_client:
                self.chat_client.cancel()
            self.chat_client = None
            self.checkpoint_chat()
            self.update_chat_transcript()
            self.refresh_chats()
            self.set_chat_busy(False)

    def cancel_chat(self, widget=None, **kwargs):
        self.chat_cancelled = True
        if self.chat_client:
            self.chat_client.cancel()
        self.chat_status.value = 'Cancelling…'

    async def export_chat(self, widget=None, **kwargs):
        from .pickers import export_document
        if self.chat_busy or self.chat_current is None:
            return
        try:
            content = export_chat(self.chat_current).encode('utf-8')
            done = await export_document(self, 'Conversation.md', content)
            self.chat_status.value = 'Conversation exported.' if done else 'Export cancelled.'
        except Exception as error:
            self.chat_status.value = 'Export failed: ' + str(error)[:400]
