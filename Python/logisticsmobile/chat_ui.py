"""Native text chat controls; only explicit user actions contact a server."""
import asyncio
from copy import deepcopy
import inspect
import time
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, END

from features.lm.domain import build_request, message, validate_settings
from .appearance import surface
from .chat import ChatStore, DEFAULT_SETTINGS, export_chat
from .chat_transport import ChatClient, ChatCancelled
from .chat_presentation import composer_height, transcript_document, transcript_entries, transcript_update


class ChatUI:
    def show_chat(self, widget=None, *, present=True, **kwargs):
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
            self.chat_render_ready = False
            self.chat_render_revision = 0
            self.chat_render_generation = 0
            self.chat_render_task = None
            self.chat_render_key = None
            self.chat_render_entries = []
            self.chat_force_latest = False
            self.chat_transcript = toga.WebView(on_navigation_starting=lambda widget, url, **kw: False,
                on_webview_load=self.chat_transcript_loaded, style=Pack(flex=1))
            self.chat_prompt = toga.MultilineTextInput(on_change=self.chat_draft_changed,
                placeholder='Message…', style=Pack(flex=1, height=52, font_size=int(self.preferences.values['font_size'])))
            self.chat_send = toga.Button('Send', on_press=self.chat_primary_action, style=Pack(width=64, height=52))
            self.chat_export = toga.Button('Export conversation…', on_press=self.export_chat, style=Pack(height=44))
            contexts = sorted({'2048', '4096', '8192', '16384', '32768', str(self.chat_profile['settings']['context_tokens'])}, key=int)
            replies = sorted({'256', '512', '1024', '2048', '4096', str(self.chat_profile['settings']['max_tokens'])}, key=int)
            self.chat_context = toga.Selection(items=contexts,
                value=str(self.chat_profile['settings']['context_tokens']), style=Pack(flex=1, height=44))
            self.chat_max_tokens = toga.Selection(items=replies,
                value=str(self.chat_profile['settings']['max_tokens']), style=Pack(flex=1, height=44))
            self.chat_status = toga.MultilineTextInput(readonly=True, style=Pack(height=44, font_size=12))
            self.chat_config_status = toga.MultilineTextInput(readonly=True, style=Pack(height=44, font_size=12))
            self.chat_config_status_box = toga.Box(style=Pack(direction=COLUMN))
            self.chat_config_view = toga.ScrollContainer(horizontal=False, content=toga.Box(children=[
                toga.Button('Back to conversation', on_press=self.show_chat, style=Pack(height=44)),
                toga.Label('Server & generation settings'), self.chat_url, self.chat_key, self.chat_model,
                toga.Label('Context tokens / maximum\nreply tokens'),
                toga.Box(children=[self.chat_context, self.chat_max_tokens], style=Pack(direction=ROW)),
                self.chat_refresh, self.chat_models, self.chat_config_status_box,
                toga.Button('Save configuration', on_press=self.save_chat_configuration, style=Pack(height=44))],
                style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))
            from .workspace_navigation import menu_button
            self.chat_title = toga.Label('New conversation', style=Pack(font_weight='bold', font_size=16))
            self.chat_model_label = toga.Label('', style=Pack(font_size=12))
            self.chat_menu_button = menu_button(self.toggle_chat_conversations, 'Conversations')
            self.chat_actions_button = toga.Button('•••', style=Pack(width=44, height=44))
            from commonUtils.ui.native.menus import NativeMenu
            self.chat_actions = NativeMenu(self.chat_actions_button, [
                ('New conversation', self.new_chat), ('Export conversation…', self.export_chat),
                ('Server & model settings', self.show_chat_configuration)], invoke=self.invoke_chat_action,
                context=lambda: self._impl.native, fallback=self.show_chat_actions)
            backend = type(self.chat_actions_button._impl).__module__
            if backend.startswith('toga_iOS.'):
                self.chat_actions_button._impl.native.accessibilityLabel = 'Conversation actions'
            elif backend.startswith('toga_android.'):
                self.chat_actions_button._impl.native.setContentDescription('Conversation actions')
            self.chat_conversation_list = toga.Box(style=Pack(direction=COLUMN))
            sidebar = toga.Box(children=[toga.Label('Conversations', style=Pack(font_size=20, margin_bottom=12)),
                self.chat_new,
                toga.ScrollContainer(horizontal=False, content=self.chat_conversation_list, style=Pack(flex=1)),
                self.chat_export], style=Pack(direction=COLUMN, flex=1, margin=12))
            self.chat_sidebar = surface(toga.Box(children=[sidebar], style=Pack(direction=COLUMN, flex=1)), radius=16)
            self.chat_status_box = toga.Box(style=Pack(direction=COLUMN))
            self.chat_composer = toga.Box(children=[self.chat_prompt, self.chat_send],
                style=Pack(direction=ROW, align_items=END, margin_top=8))
            self.chat_transcript_card = surface(toga.Box(children=[toga.Box(children=[self.chat_transcript],
                style=Pack(direction=COLUMN, flex=1, margin=10))], style=Pack(direction=COLUMN, flex=1)), radius=16)
            surface(self.chat_prompt, radius=12)
            self.chat_messages = toga.Box(children=[self.chat_transcript_card, self.chat_status_box, self.chat_composer],
                style=Pack(direction=COLUMN, flex=1))
            self.chat_workspace = toga.Box(style=Pack(direction=ROW, flex=1))
            self.chat_drawer_open = self.adaptive.width() >= 640
            self.chat_header = toga.Box(children=[self.chat_menu_button,
                toga.Box(children=[self.chat_title, self.chat_model_label], style=Pack(direction=COLUMN, flex=1, margin_left=4)),
                self.chat_actions_button],
                style=Pack(direction=ROW, margin_bottom=8))
            self.chat_view = toga.Box(children=[self.chat_header, self.chat_workspace],
                style=Pack(direction=COLUMN, margin=12, flex=1))
            self.refresh_chats()
            if self.chat_labels:
                self.open_chat(next(iter(self.chat_labels.values())))
            else:
                self.new_chat()
            if error:
                self.set_chat_status(error)
            self.chat_transcript.set_content('https://logistics.invalid/chat/', transcript_document())
        self.chat_prompt.style.font_size = int(self.preferences.values['font_size'])
        self.update_chat_transcript()
        if present:
            self.show_view(self.chat_view, destination='chat', root=True, title='Chat')
        else:
            # The native tab callback is already selecting Chat. Mount its lazy
            # content without starting a second native selection mid-transition.
            root = self.routes.roots['chat']
            if list(root.children) != [self.chat_view]:
                for child in list(root.children):
                    root.remove(child)
                root.add(self.chat_view)
            self.render_chat_workspace()

    def toggle_chat_conversations(self, widget=None, **kwargs):
        self.chat_drawer_open = not self.chat_drawer_open
        self.render_chat_workspace()

    def render_chat_workspace(self):
        if not hasattr(self, 'chat_workspace'):
            return
        children = []
        if self.chat_drawer_open:
            children.append(self.chat_sidebar)
        if not self.chat_drawer_open or self.adaptive.width() >= 640:
            children.append(self.chat_messages)
        if list(self.chat_workspace.children) != children:
            for child in list(self.chat_workspace.children):
                self.chat_workspace.remove(child)
            self.chat_workspace.add(*children)
        if len(children) == 2:
            available = self.adaptive.content_width('chat')
            half = max(1, int(available / 2))
            self.chat_sidebar.style.width, self.chat_sidebar.style.flex = half, 0
            self.chat_messages.style.width, self.chat_messages.style.flex = max(1, int(available) - half), 0
        else:
            for child in children:
                del child.style.width
                child.style.flex = 1
        self.sync_chat_navigation()
        self.reserve_chat_navigation()
        self.update_chat_header()
        self.resize_chat_composer()

    def sync_chat_navigation(self):
        """Place the iPhone drawer in the same native bar as Documents' menu."""
        if not self.routes.apple or self.chat_view not in self.routes.body('chat').children:
            return
        from rubicon.objc import ObjCClass, SEL
        if self.chat_menu_button in self.chat_header.children:
            self.chat_header.remove(self.chat_menu_button)
        self.chat_menu_button.app, self.chat_menu_button.window = self, self.main_window
        if not hasattr(self, 'chat_native_menu'):
            self.chat_native_menu = ObjCClass('UIBarButtonItem').alloc().initWithImage(
                ObjCClass('UIImage').systemImageNamed('line.3.horizontal'), style=0,
                target=self.chat_menu_button._impl.native, action=SEL('onPress:'))
        index = self.native_host.destinations.index('chat')
        controller = self.native_host.adapter.navigation[index].topViewController
        controller.navigationItem.leftBarButtonItem = self.chat_native_menu
        self.chat_native_menu.accessibilityLabel = 'Close conversations' if self.chat_drawer_open else 'Conversations'

    def reserve_chat_navigation(self):
        """The floating UIKit tab bar can extend above its reported safe inset."""
        adapter = self.native_host.adapter
        if adapter is None or not hasattr(adapter, 'navigation'):
            return
        container = self.chat_view._impl.container
        if container is None or container.native.bounds.size.height <= 0:
            return
        tab = adapter.controller.tabBar
        if tab.isHidden():
            margin = 12
        else:
            window = self.main_window._impl.native
            viewport = container.native.convertRect(container.native.bounds, toView=window)
            bar = tab.convertRect(tab.bounds, toView=window)
            bottom = float(viewport.origin.y + viewport.size.height - container.bottom_inset)
            top = float(viewport.origin.y + container.top_inset)
            from .chat_presentation import navigation_clearance
            margin = navigation_clearance(top, bottom, float(bar.origin.y), float(bar.size.height))
        if self.chat_view.style.margin_bottom != margin:
            self.chat_view.style.margin_bottom = margin

    def update_chat_header(self):
        sidebar = self.chat_drawer_open and self.adaptive.width() < 640
        title = (self.chat_current or {}).get('title', 'New conversation')
        # A bounded, two-line native heading must not dictate the pane width.
        available = self.chat_view.layout.content_width or max(1, self.adaptive.width() - 24)
        limit = max(12, int((available - 112) / 9))
        self.chat_title.text = 'Conversations' if sidebar else title[:limit] + ('…' if len(title) > limit else '')
        model = self.chat_profile.get('model') or 'Set up a server'
        self.chat_model_label.text = model[:limit] + ('…' if len(model) > limit else '')

    def resize_chat_composer(self):
        if not hasattr(self, 'chat_messages'):
            return
        width = self.chat_messages.layout.content_width or max(1, self.adaptive.width() - 24)
        self.chat_prompt.style.height = composer_height(self.chat_prompt.value, width - 64,
                                                       int(self.preferences.values['font_size']))

    def set_chat_status(self, value):
        for status, box in ((self.chat_status, self.chat_status_box),
                            (self.chat_config_status, self.chat_config_status_box)):
            status.value = value
            if value and status not in box.children:
                box.add(status)
            elif not value and status in box.children:
                box.remove(status)

    def show_chat_actions(self, widget=None, **kwargs):
        box = toga.Box(children=[
            toga.Button('Back to conversation', on_press=self.show_chat, style=Pack(height=44)),
            toga.Button('New conversation', on_press=self.new_chat_from_actions, style=Pack(height=44)),
            toga.Button('Export conversation…', on_press=self.export_chat, style=Pack(height=44)),
            toga.Button('Server & model settings', on_press=self.show_chat_configuration, style=Pack(height=44))],
            style=Pack(direction=COLUMN, margin=12))
        self.show_view(box, destination='chat', route='chat-actions', title='Conversation')

    def new_chat_from_actions(self, widget=None, **kwargs):
        self.new_chat()
        self.show_chat()

    def invoke_chat_action(self, callback):
        if self.chat_busy or not self.active_host:
            return
        result = callback()
        if inspect.isawaitable(result):
            self.loop.create_task(result)

    def show_chat_messages(self):
        if self.adaptive.width() < 640:
            self.chat_drawer_open = False
        self.render_chat_workspace()

    def show_chat_configuration(self, widget=None, **kwargs):
        if not hasattr(self, 'chat_store'):
            self.show_chat()
        self.show_view(self.chat_config_view, destination='chat', route='chat-settings', title='Chat settings')

    def save_chat_configuration(self, widget=None, **kwargs):
        if self.chat_busy:
            return
        try:
            self.chat_fields()
            self.set_chat_status('Configuration saved. The API key stays in this session only.')
            self.show_chat()
        except (OSError, ValueError) as error:
            self.set_chat_status(str(error))
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
        from commonUtils.ui.native.presentation import list_button
        for child in list(self.chat_conversation_list.children):
            self.chat_conversation_list.remove(child)
        self.chat_conversation_buttons = []
        for label, key in labels.items():
            def select(widget=None, selected=key, **kwargs):
                self.open_chat(selected)
            current = self.chat_current is not None and self.chat_current['id'] == key
            button = list_button(toga.Button(('● ' if current else '') + label, on_press=select,
                enabled=not self.chat_busy, style=Pack(height=48, margin_bottom=4)))
            self.chat_conversation_list.add(button)
            self.chat_conversation_buttons.append(button)
        if warnings:
            self.set_chat_status(f'{len(warnings)} conversation(s) could not be read; originals preserved.')

    def checkpoint_chat(self):
        if self.chat_current is None:
            return True
        try:
            self.chat_store.save(self.chat_current)
            return True
        except (OSError, ValueError) as error:
            self.set_chat_status('Chat not saved: ' + str(error))
            return False

    def open_chat(self, key):
        if self.chat_busy or not self.checkpoint_chat():
            return
        try:
            self.chat_current = self.chat_store.load(key)
            self.chat_loading = True
            self.chat_prompt.value = self.chat_current['draft']
            self.chat_loading = False
            self.set_chat_status('')
            self.update_chat_transcript()
            self.refresh_chats()
            self.show_chat_messages()
        except (OSError, ValueError) as error:
            self.set_chat_status(str(error))

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
            self.set_chat_status('')
            self.update_chat_transcript()
            self.refresh_chats()
            self.show_chat_messages()
        except (OSError, ValueError) as error:
            self.set_chat_status(str(error))

    def chat_draft_changed(self, widget, **kwargs):
        self.resize_chat_composer()
        if not self.chat_loading and self.chat_current is not None:
            self.chat_current['draft'] = widget.value
            self.checkpoint_chat()

    def update_chat_transcript(self):
        self.chat_render_revision += 1
        self.update_chat_header()
        self.schedule_chat_render()

    def chat_transcript_loaded(self, widget=None, **kwargs):
        self.chat_render_ready = True
        self.chat_render_revision += 1
        self.chat_render_generation += 1
        self.chat_render_key = None
        self.chat_render_entries = []
        self.schedule_chat_render()

    def schedule_chat_render(self):
        if self.chat_render_ready and (self.chat_render_task is None or self.chat_render_task.done()):
            self.chat_render_task = self.loop.create_task(self.render_chat_transcript())

    async def render_chat_transcript(self):
        rendered = -1
        try:
            while rendered != self.chat_render_revision:
                rendered = self.chat_render_revision
                generation = self.chat_render_generation
                data = self.chat_current
                if data is None:
                    return
                force_latest, self.chat_force_latest = self.chat_force_latest, False
                previous = self.chat_render_entries if self.chat_render_key == data['id'] else []
                entries = transcript_entries(data['messages'], previous)
                start = 0
                while start < min(len(entries), len(previous)) and entries[start] is previous[start]:
                    start += 1
                script = transcript_update(data['id'], entries[start:],
                    self.preferences.values['font_size'],
                    configured=bool(self.chat_profile['base_url'] and self.chat_profile['model']),
                    force_latest=force_latest, start=start)
                ready = await self.chat_transcript.evaluate_javascript(script)
                if not ready:
                    # The initial blank-page load may finish before set_content.
                    # Its next real load event will render the current record.
                    if rendered == self.chat_render_revision:
                        self.chat_render_ready = False
                        return
                elif generation == self.chat_render_generation:
                    self.chat_render_key, self.chat_render_entries = data['id'], entries
        except (RuntimeError, ValueError) as error:
            self.set_chat_status('Conversation display unavailable: ' + str(error)[:200])

    async def chat_primary_action(self, widget=None, **kwargs):
        if self.chat_busy:
            if self.chat_generating:
                self.cancel_chat()
        else:
            await self.send_chat()

    def set_chat_busy(self, busy, *, generating=False):
        self.chat_busy = busy
        self.chat_generating = busy and generating
        for control in (self.chat_url, self.chat_key, self.chat_model, self.chat_models, self.chat_selector,
                        self.chat_new, self.chat_refresh, self.chat_export, self.chat_actions_button,
                        self.chat_context, self.chat_max_tokens):
            control.enabled = not busy
        self.chat_send.text = 'Stop' if self.chat_generating else 'Send'
        self.chat_send.enabled = not busy or self.chat_generating
        for control in self.chat_conversation_buttons:
            control.enabled = not busy

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
            self.set_chat_status(f'{len(models)} model(s) available.' if models else 'No models are loaded on the server.')
        except Exception as error:
            self.set_chat_status('Models unavailable: ' + str(error)[:400])
        finally:
            self.chat_client = None
            self.set_chat_busy(False)

    async def send_chat(self, widget=None, **kwargs):
        if self.chat_busy or self.chat_current is None:
            return
        prompt = self.chat_prompt.value.strip()
        if not prompt:
            self.set_chat_status('Enter a message first.')
            return
        if len(self.chat_current['messages']) > 198:
            self.set_chat_status('This conversation has reached 200 messages. Start a new conversation.')
            return
        self.set_chat_busy(True, generating=True)
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
            self.resize_chat_composer()
            if not self.checkpoint_chat():
                data.clear()
                data.update(before)
                assistant = None
                self.chat_loading = True
                self.chat_prompt.value = data['draft']
                self.chat_loading = False
                raise ValueError('The request was not sent because its recovery record could not be saved.')
            self.chat_force_latest = True
            self.update_chat_transcript()
            omitted = metadata['omitted_turns']
            self.set_chat_status(f'Generating… {omitted} older turn(s) omitted from context.' if omitted else 'Generating…')
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
            self.set_chat_status('Reply stopped; partial text preserved.' if self.chat_cancelled else '')
        except ChatCancelled:
            if assistant:
                assistant['status'] = 'cancelled'
            self.set_chat_status('Request cancelled; partial text preserved.')
        except asyncio.CancelledError:
            if assistant:
                assistant['status'] = 'interrupted'
            raise
        except Exception as error:
            if assistant:
                assistant['status'] = 'failed'
                assistant['error'] = str(error)[:400]
            self.set_chat_status('Chat failed: ' + str(error)[:400])
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
        self.chat_send.enabled = False
        self.set_chat_status('Stopping…')

    async def export_chat(self, widget=None, **kwargs):
        from .pickers import export_document
        if self.chat_busy or self.chat_current is None:
            return
        try:
            content = export_chat(self.chat_current).encode('utf-8')
            done = await export_document(self, 'Conversation.md', content)
            self.set_chat_status('Conversation exported.' if done else 'Export cancelled.')
        except Exception as error:
            self.set_chat_status('Export failed: ' + str(error)[:400])
