"""Native text chat controls; only explicit user actions contact a server."""
from commonUtils.ui.native.password_input import PasswordInput
import asyncio
from copy import deepcopy
import inspect
import time
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, END

from features.lm.domain import build_request, conversation, message, validate_settings
from features.lm.mobile.storage import ChatStore, DEFAULT_SETTINGS, export_chat
from features.lm.mobile.transport import ChatClient, ChatCancelled
from features.lm.mobile.presentation import composer_height, transcript_document, transcript_entries, transcript_update


class ChatTranscript(toga.WebView):
    # The transcript scrolls internally. Its default 100dp minimum must not
    # push the composer outside the smaller viewport above a phone keyboard.
    _MIN_HEIGHT = 0


class ChatUI:
    def show_chat(self, widget=None, *, present=True, **kwargs):
        if not self.app.require_feature('lm', destination='chat', present=present):
            return
        if not hasattr(self, 'chat_store'):
            self.chat_store = ChatStore(self.private_root / 'LM')
            self.state.current = None
            self.state.busy = self.state.loading = False
            self.state.client = None
            self.chat_labels = {}
            try:
                self.chat_profile, self.chat_profile_original = self.chat_store.profile()
                error = ''
            except (OSError, ValueError) as problem:
                self.chat_profile = dict(schema=1, base_url='', model='', settings=dict(DEFAULT_SETTINGS))
                self.chat_profile_original = None
                error = str(problem)
            self._build_chat_controls()
            self._build_chat_configuration()
            self._build_chat_workspace()
            self.state.needs_initial_selection = True
            self.refresh_chats()
            if error:
                self.set_chat_status(error)
            self.chat_transcript.set_content('https://logistics.invalid/chat/', transcript_document(theme_css=self.presentation.css_variables()))
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

    def _build_chat_controls(self):
        """Build retained connection, transcript and composer input controls."""
        self.chat_url = toga.TextInput(value=self.chat_profile['base_url'],
            placeholder='e.g. http://192.168.1.10:1234', style=Pack(height=48))
        self.chat_key = PasswordInput(placeholder='API key (session only)', style=Pack(height=48))
        self.chat_model = toga.TextInput(value=self.chat_profile['model'], placeholder='Filled after connecting, or enter a model ID', style=Pack(height=48))
        self.chat_models = toga.Selection(on_change=self.select_chat_model, style=Pack(height=48))
        self.chat_refresh = toga.Button('Connect & load models', on_press=self.refresh_chat_models, style=Pack(height=48))
        self.chat_selector = toga.Selection(on_change=self.select_chat, style=Pack(height=48))
        self.chat_new = self.presentation.surface(toga.Button('New chat', on_press=self.new_chat,
            style=Pack(height=52, width=148, font_size=17, font_weight='bold')),
            radius=26, background='chat_background', foreground='text', outlined=True)
        self.transcript.ready = False
        self.transcript.revision = 0
        self.transcript.generation = 0
        self.transcript.task = None
        self.transcript.key = None
        self.transcript.entries = []
        self.transcript.force_latest = False
        self.chat_transcript = ChatTranscript(on_navigation_starting=lambda widget, url, **kw: False,
            on_webview_load=self.chat_transcript_loaded, style=Pack(flex=1))
        self.presentation.surface(self.chat_transcript, radius=0, background='chat_background', outlined=False)
        self.chat_prompt = toga.MultilineTextInput(on_change=self.chat_draft_changed,
            placeholder='Message…', style=Pack(flex=1, height=52, margin=4, margin_left=12, font_size=int(self.preferences.values['font_size'])))
        self.chat_send = self.presentation.icon_button('up', 'Send', on_press=self.chat_primary_action)
        self.chat_send.style.margin = 6
        self.chat_export = toga.Button('Export conversation…', on_press=self.export_chat, style=Pack(height=48))

    def _build_chat_configuration(self):
        """Build session-key and generation settings without contacting the server."""
        contexts = sorted({'2048', '4096', '8192', '16384', '32768', str(self.chat_profile['settings']['context_tokens'])}, key=int)
        replies = sorted({'256', '512', '1024', '2048', '4096', str(self.chat_profile['settings']['max_tokens'])}, key=int)
        self.chat_context = toga.Selection(items=contexts,
            value=str(self.chat_profile['settings']['context_tokens']), style=Pack(flex=1, height=48))
        self.chat_max_tokens = toga.Selection(items=replies,
            value=str(self.chat_profile['settings']['max_tokens']), style=Pack(flex=1, height=48))
        self.chat_status = toga.MultilineTextInput(readonly=True, style=Pack(height=48, font_size=12))
        self.chat_config_status = toga.MultilineTextInput(readonly=True, style=Pack(height=48, font_size=12))
        self.chat_config_status_box = toga.Box(style=Pack(direction=COLUMN))
        self.chat_config_view = toga.ScrollContainer(horizontal=False, content=toga.Box(children=[
            toga.Button('Back to conversation', on_press=self.show_chat, style=Pack(height=48)),
            toga.Label('Server API URL'), self.chat_url,
            toga.Label('A plain address uses /v1 automatically.\nFor a computer server, use its LAN address.', style=Pack(font_size=12)),
            toga.Label('API key (optional; session only)'), self.chat_key,
            self.chat_refresh, self.chat_config_status_box,
            toga.Label('Model'), self.chat_models,
            toga.Label('Choose a model above, or enter its exact ID below.', style=Pack(font_size=12)), self.chat_model,
            toga.Label('Generation settings (defaults work for most servers)'),
            toga.Label('Context tokens / maximum\nreply tokens'),
            toga.Box(children=[self.chat_context, self.chat_max_tokens], style=Pack(direction=ROW)),
            toga.Button('Save & return to chat', on_press=self.save_chat_configuration, style=Pack(height=48))],
            style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))

    def _build_chat_workspace(self):
        """Assemble the retained header, conversation drawer and message workspace."""
        self.chat_title = toga.Label('New conversation', style=Pack(font_weight='bold', font_size=16))
        self.chat_model_label = toga.Label('', style=Pack(font_size=12))
        for label in (self.chat_title, self.chat_model_label):
            backend = type(label._impl).__module__
            if backend.startswith('toga_iOS.'):
                label._impl.native.numberOfLines = 1
                label._impl.native.lineBreakMode = 4
            elif backend.startswith('toga_android.'):
                from android.text import TextUtils
                label._impl.native.setSingleLine(True)
                label._impl.native.setEllipsize(TextUtils.TruncateAt.END)
        self.chat_menu_button = self.presentation.menu_button(self.toggle_chat_conversations, 'Conversations')
        self.chat_header_new = self.presentation.icon_button('compose', 'New conversation', on_press=self.new_chat)
        self.chat_actions_button = self.presentation.icon_button('more', 'Conversation actions')
        self.chat_actions = self.presentation.NativeMenu(self.chat_actions_button, [
            ('New conversation', self.new_chat), ('Export conversation…', self.export_chat),
            ('Server & model settings', self.show_chat_configuration)], invoke=self.invoke_chat_action,
            context=lambda: self._impl.native, fallback=self.show_chat_actions)
        backend = type(self.chat_actions_button._impl).__module__
        if backend.startswith('toga_iOS.'):
            self.chat_actions_button._impl.native.accessibilityLabel = 'Conversation actions'
        elif backend.startswith('toga_android.'):
            self.chat_actions_button._impl.native.setContentDescription('Conversation actions')
        self.chat_conversation_list = self.presentation.summary_list(kind='Conversation',
            icon_kind='chat', on_select=self._select_conversation_row, style=Pack(flex=1))
        self.chat_conversation_buttons = []  # Compatibility; rows are recycled natively.
        self.chat_drawer_settings = self.presentation.icon_button('preferences' if self.routes.apple else 'more', 'Chat settings', on_press=self.show_chat_configuration)
        self.chat_sidebar_title = toga.Label('Conversations',
            style=Pack(font_size=22, font_weight='bold', margin_bottom=20))
        self.chat_sidebar_content = sidebar = toga.Box(children=[self.chat_sidebar_title,
            self.chat_conversation_list,
            toga.Box(children=[self.chat_new, toga.Box(style=Pack(flex=1)), self.chat_drawer_settings],
                     style=Pack(direction=ROW, margin_top=16))],
            style=Pack(direction=COLUMN, flex=1, margin=16))
        self.chat_sidebar = self.presentation.surface(toga.Box(children=[sidebar], style=Pack(direction=COLUMN, flex=1)),
                                    radius=0, background='chat_background', outlined=False)
        self.chat_status_box = toga.Box(style=Pack(direction=COLUMN))
        self.chat_composer = toga.Box(children=[self.chat_prompt, self.chat_send],
            style=Pack(direction=ROW, align_items=END, margin_top=12, margin_bottom=4))
        self.presentation.surface(self.chat_composer, radius=30, background='chat_input', outlined=False)
        self.chat_setup = self.presentation.action_button(toga.Button('Set up chat', on_press=self.show_chat_configuration,
                                                    style=Pack(height=48, margin_bottom=8)))
        self.chat_setup_box = toga.Box(style=Pack(direction=COLUMN))
        self.chat_transcript_card = toga.Box(children=[self.chat_transcript], style=Pack(direction=COLUMN, flex=1))
        self.presentation.surface(self.chat_prompt, radius=22, background='chat_input', foreground='text', outlined=False)
        self.presentation.surface(self.chat_send, radius=24, background='chat_primary', foreground='chat_on_primary', outlined=False)
        self.presentation.surface(self.chat_status, radius=0, background='chat_background', foreground='muted', outlined=False)
        self.chat_messages = toga.Box(children=[self.chat_transcript_card, self.chat_status_box, self.chat_composer],
            style=Pack(direction=COLUMN, flex=1))
        self.chat_workspace = toga.Box(style=Pack(direction=ROW, flex=1))
        self.chat_drawer_open = self.adaptive.width() >= 640
        for control in (self.chat_header_new, self.chat_actions_button):
            self.presentation.surface(control, radius=24, background='chat_input', foreground='text', outlined=False)
        self.chat_header_actions = self.presentation.surface(toga.Box(children=[self.chat_header_new, self.chat_actions_button],
            style=Pack(direction=ROW)), radius=24, background='chat_input', outlined=False)
        self.chat_header = toga.Box(children=[self.chat_menu_button,
            toga.Box(children=[self.chat_title, self.chat_model_label], style=Pack(direction=COLUMN, flex=1, margin_left=4)),
            self.chat_header_actions],
            style=Pack(direction=ROW, margin_bottom=12))
        self.chat_view = toga.Box(children=[self.chat_header, self.chat_setup_box, self.chat_workspace],
            style=Pack(direction=COLUMN, margin=12, flex=1))
        self.presentation.surface(self.chat_view, radius=0, background='chat_background', outlined=False)
        # The host mounts screen actions in its native iOS navigation bar.
        # Content/header/composer ownership remains unchanged on Android.
        self.chat_view._ios_toolbar_buttons = [self.chat_header_new, self.chat_actions_button]
        self.chat_view._ios_toolbar_leading = [self.chat_menu_button]
        self.chat_view._ios_toolbar_hidden = [self.chat_header_actions]

    def toggle_chat_conversations(self, widget=None, **kwargs):
        self.chat_drawer_open = not self.chat_drawer_open
        self.render_chat_workspace()

    def render_chat_workspace(self):
        if not hasattr(self, 'chat_workspace'):
            return
        compact_drawer = self.chat_drawer_open and self.adaptive.width() < 640
        sidebar_children = self.chat_sidebar_content.children
        if compact_drawer and self.chat_sidebar_title in sidebar_children:
            self.chat_sidebar_content.remove(self.chat_sidebar_title)
        elif not compact_drawer and self.chat_sidebar_title not in sidebar_children:
            self.chat_sidebar_content.insert(0, self.chat_sidebar_title)
        self.presentation.surface(self.chat_view, radius=0,
                background='chat_background', outlined=False)
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
        self.sync_chat_appearance()
        self.update_chat_header()
        self.update_chat_readiness()
        self.resize_chat_composer()

    def update_chat_readiness(self):
        configured = bool(self.chat_profile.get('base_url') and self.chat_profile.get('model'))
        hide_setup = configured or (self.chat_drawer_open and self.adaptive.width() < 640)
        if hide_setup and self.chat_setup in self.chat_setup_box.children:
            self.chat_setup_box.remove(self.chat_setup)
        elif not hide_setup and self.chat_setup not in self.chat_setup_box.children:
            self.chat_setup_box.add(self.chat_setup)
        generating = self.state.generating
        self.chat_send.enabled = generating or (configured and not self.state.busy)
        self.chat_setup.enabled = not self.state.busy

    def sync_chat_navigation(self):
        """Place the iPhone drawer in the same native bar as Documents' menu."""
        if not self.routes.apple or self.chat_view not in self.routes.body('chat').children:
            return
        # Native controls are mounted by the application's screen-toolbar pass.
        # The semantic title and drawer label remain feature-owned.
        self.chat_menu_button._workspace_menu_label = (
            'Close conversations' if self.chat_drawer_open else 'Conversations')
        self.chat_menu_button.accessible_name = self.chat_menu_button._workspace_menu_label
        self.chat_view._ios_toolbar_leading = [self.chat_menu_button]

    def reserve_chat_navigation(self):
        """The floating UIKit tab bar can extend above its reported safe inset."""
        adapter = self.native_host.adapter
        if adapter is None or not hasattr(adapter, 'navigation'):
            return
        container = self.chat_view._impl.container
        if container is None or container.native.bounds.size.height <= 0:
            return
        tab = adapter.controller.tabBar
        hidden = adapter.tabs_hidden() if hasattr(adapter, 'tabs_hidden') else bool(tab.isHidden())
        if hidden:
            margin = 12
        else:
            window = self.main_window._impl.native
            viewport = container.native.convertRect(container.native.bounds, toView=window)
            bar = tab.convertRect(tab.bounds, toView=window)
            bottom = float(viewport.origin.y + viewport.size.height - container.bottom_inset)
            top = float(viewport.origin.y + container.top_inset)
            from features.lm.mobile.presentation import navigation_clearance
            margin = navigation_clearance(top, bottom, float(bar.origin.y), float(bar.size.height),
                                          bar_width=float(bar.size.width))
        # Vertical Duo bars do not reserve the Home-indicator strip through
        # the content container. Keep the fixed composer within the window's
        # actual bottom safe area without double-counting horizontal tab bars.
        window = self.main_window._impl.native
        viewport = container.native.convertRect(container.native.bounds, toView=window)
        bottom = float(viewport.origin.y + viewport.size.height - container.bottom_inset)
        safe_bottom = float(window.bounds.size.height - window.safeAreaInsets.bottom)
        margin = max(margin, 12 + max(0, bottom - safe_bottom))
        if self.chat_view.style.margin_bottom != margin:
            self.chat_view.style.margin_bottom = margin

    def update_chat_header(self):
        sidebar = self.chat_drawer_open and self.adaptive.width() < 640
        title = (self.state.current or {}).get('title', 'New conversation')
        # Native ellipsis and explicit bounds stop long titles pushing the
        # action capsule outside the safe-area allocation on iPad and Duo.
        available = self.adaptive.content_width('chat')
        menu_width = 52 if self.chat_menu_button in self.chat_header.children else 0
        title_width = max(24, int(available) - 96 - menu_width - 12)
        for label in (self.chat_title, self.chat_model_label):
            if label.style.width != title_width:
                label.style.width = title_width
        for label, text in ((self.chat_title, 'Conversations' if sidebar else title),
                            (self.chat_model_label, '' if sidebar else self.chat_profile.get('model') or 'Set up a server')):
            if label.text != text:
                label.text = text

    def resize_chat_composer(self):
        if not hasattr(self, 'chat_messages'):
            return
        width = self.adaptive.content_width('chat')
        if self.chat_drawer_open and self.adaptive.width() >= 640:
            width /= 2
        inset = max(0, int((width - 780) / 2))
        self.chat_composer.style.margin_left = self.chat_composer.style.margin_right = inset
        self.chat_status_box.style.margin_left = self.chat_status_box.style.margin_right = inset
        container = self.chat_view._impl.container
        available_height = container.height if container is not None else 0
        self.chat_prompt.style.height = composer_height(self.chat_prompt.value, min(width, 780) - 84,
            int(self.preferences.values['font_size']), available_height=available_height or None)

    def sync_chat_appearance(self):
        """Match the navigation/status area to Chat without moving its menu."""
        if not self.routes.apple:
            return
        from rubicon.objc import ObjCClass
        self.presentation.surface(self.routes.roots['chat'], radius=0, background='chat_background', outlined=False)
        navigation = self.native_host.adapter.navigation[self.native_host.destinations.index('chat')]
        color = self.presentation.apple_color('chat_background')
        navigation.view.backgroundColor = color
        bar = navigation.navigationBar
        if not hasattr(self, 'chat_bar_appearance'):
            self.chat_bar_appearance = ObjCClass('UINavigationBarAppearance').alloc().init()
            self.chat_bar_appearance.configureWithOpaqueBackground()
            self.chat_bar_appearance.backgroundColor = color
            self.chat_bar_appearance.shadowColor = ObjCClass('UIColor').clearColor
        bar.standardAppearance = self.chat_bar_appearance
        bar.scrollEdgeAppearance = self.chat_bar_appearance
        bar.compactAppearance = self.chat_bar_appearance
        bar.tintColor = self.presentation.apple_color('text')

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
            toga.Button('Back to conversation', on_press=self.show_chat, style=Pack(height=48)),
            toga.Button('New conversation', on_press=self.new_chat_from_actions, style=Pack(height=48)),
            toga.Button('Export conversation…', on_press=self.export_chat, style=Pack(height=48)),
            toga.Button('Server & model settings', on_press=self.show_chat_configuration, style=Pack(height=48))],
            style=Pack(direction=COLUMN, margin=12))
        self.show_view(box, destination='chat', route='chat-actions', title='Conversation')

    def new_chat_from_actions(self, widget=None, **kwargs):
        self.new_chat()
        self.show_chat()

    def invoke_chat_action(self, callback):
        if self.state.busy or not self.active_host:
            return
        result = callback()
        if inspect.isawaitable(result):
            self.loop.create_task(result)

    def show_chat_messages(self):
        if self.adaptive.width() < 640:
            self.chat_drawer_open = False
        self.render_chat_workspace()

    def show_chat_configuration(self, widget=None, **kwargs):
        if not self.app.require_feature('lm', destination='chat'):
            return
        if not hasattr(self, 'chat_store'):
            self.show_chat()
        self.show_view(self.chat_config_view, destination='chat', route='chat-settings', title='Chat settings')

    def save_chat_configuration(self, widget=None, **kwargs):
        if self.state.busy:
            return
        try:
            if not self.chat_model.value.strip():
                raise ValueError('Connect & load models, then choose a model, or enter its exact ID.')
            self.chat_fields()
            self.set_chat_status('Configuration saved. The API key stays in this session only.')
            self.show_chat()
        except (OSError, ValueError) as error:
            self.set_chat_status(str(error))

    def refresh_chats(self):
        try:
            asyncio.get_running_loop()
            asynchronous = True
        except RuntimeError:
            asynchronous = type(self._impl).__module__.startswith(('toga_iOS.', 'toga_android.'))
        if not asynchronous:
            self._publish_chat_inventory(*self.chat_store.summaries(), authoritative=True)
            return
        self._publish_chat_inventory(*self.chat_store.cached_summaries())
        self.state.inventory_again = True
        task = self.state.inventory_task
        if task is None or task.done():
            async def refresh():
                while self.active_host and self.state.inventory_again:
                    self.state.inventory_again = False
                    records, warnings = await asyncio.to_thread(self.chat_store.summaries)
                    if self.active_host and not self.state.inventory_again:
                        self._publish_chat_inventory(records, warnings, authoritative=True)
            self.state.inventory_task = self.loop.create_task(refresh())

    def _publish_chat_inventory(self, records, warnings, *, authoritative=False):
        self.state.loading = True
        labels = {}
        for record in records:
            label = record['title'][:60]
            while label in labels:
                label += ' (copy)'
            labels[label] = record['id']
        self.chat_labels = labels
        self.chat_selector.items = list(labels)
        if self.state.current:
            selected_label = next((label for label, key in labels.items() if key == self.state.current['id']), None)
            if selected_label is not None:
                self.chat_selector.value = selected_label
        self.state.loading = False
        self._project_chat_rows(labels)
        if warnings:
            self.set_chat_status(f'{len(warnings)} conversation(s) could not be read; originals preserved.')
        if (authoritative and not self.state.busy
                and self.state.needs_initial_selection):
            self.state.needs_initial_selection = False
            if self.chat_labels:
                self.open_chat(next(iter(self.chat_labels.values())))
            else:
                self.new_chat()

    def _project_chat_rows(self, labels):
        """Project a detached inventory while suppressing native selection callbacks."""
        listing = self.chat_conversation_list
        listing.updating = True
        try:
            listing.data = [dict(title=label, subtitle='', key=key, index=index,
                folder=False, thumbnail=False, icon=listing.row_icon)
                for index, (label, key) in enumerate(labels.items())]
            selected = next((index for index, row in enumerate(listing.data)
                if self.state.current is not None and row.key == self.state.current['id']), None)
            listing.select_index(selected)
        finally:
            listing.updating = False

    def _select_conversation_row(self, widget, **kwargs):
        if widget.updating or self.state.busy:
            return
        row = widget.selection
        if (row is not None and row.key in self.chat_labels.values()
                and (self.state.current is None or row.key != self.state.current['id'])):
            self.open_chat(row.key)

    def checkpoint_chat(self):
        if self.state.current is None:
            return True
        try:
            self.chat_store.save(self.state.current)
            return True
        except (OSError, ValueError) as error:
            self.set_chat_status('Chat not saved: ' + str(error))
            return False

    def open_chat(self, key):
        if self.state.busy or not self.checkpoint_chat():
            return
        self.state.needs_initial_selection = False
        try:
            self.state.current = self.chat_store.load(key)
            self.state.loading = True
            self.chat_prompt.value = self.state.current['draft']
            self.state.loading = False
            self.set_chat_status('')
            self.update_chat_transcript()
            self.refresh_chats()
            self.show_chat_messages()
        except (OSError, ValueError) as error:
            self.set_chat_status(str(error))

    def select_chat(self, widget, **kwargs):
        if not self.state.loading and not self.state.busy and widget.value in self.chat_labels:
            key = self.chat_labels[widget.value]
            # Android can deliver programmatic selection notifications after
            # chat_loading clears. Reopening the current chat republishes its
            # inventory and schedules another notification indefinitely.
            if self.state.current is None or key != self.state.current['id']:
                self.open_chat(key)

    def new_chat(self, widget=None, **kwargs):
        if self.state.busy or not self.checkpoint_chat():
            return
        self.state.needs_initial_selection = False
        try:
            self.state.current = self.chat_store.new(self.chat_profile['settings'])
            self.state.loading = True
            self.chat_prompt.value = ''
            self.state.loading = False
            self.set_chat_status('')
            self.update_chat_transcript()
            self.refresh_chats()
            self.show_chat_messages()
        except (OSError, ValueError) as error:
            self.set_chat_status(str(error))

    def chat_draft_changed(self, widget, **kwargs):
        self.resize_chat_composer()
        if (not self.state.loading and widget.value and self.state.current is None
                and self.state.needs_initial_selection):
            # Typing wins over a cold inventory result. Keep the new draft in
            # memory and use the normal queued save instead of opening an older
            # conversation (or clearing the composer) when discovery completes.
            self.state.needs_initial_selection = False
            self.state.current = conversation(self.chat_profile['settings'], profile_id='mobile')
        if not self.state.loading and self.state.current is not None:
            self.state.current['draft'] = widget.value
            self.chat_store.queue_save(self.state.current, self.loop,
                failed=lambda error: self.set_chat_status('Chat not saved: ' + str(error))
                    if self.active_host else None)

    def update_chat_transcript(self):
        self.transcript.revision += 1
        self.update_chat_header()
        self.schedule_chat_render()

    def chat_transcript_loaded(self, widget=None, **kwargs):
        self.transcript.ready = True
        self.transcript.revision += 1
        self.transcript.generation += 1
        self.transcript.key = None
        self.transcript.entries = []
        self.schedule_chat_render()

    def schedule_chat_render(self):
        if self.transcript.ready and (self.transcript.task is None or self.transcript.task.done()):
            self.transcript.task = self.loop.create_task(self.render_chat_transcript())

    async def render_chat_transcript(self):
        rendered = -1
        try:
            while rendered != self.transcript.revision:
                rendered = self.transcript.revision
                generation = self.transcript.generation
                data = self.state.current
                if data is None:
                    return
                if data['messages'] and data['messages'][-1]['status'] == 'streaming':
                    # One renderer owns each WebView; merge bursts while keeping
                    # all native control access on the UI loop.
                    await asyncio.sleep(.08)
                force_latest, self.transcript.force_latest = self.transcript.force_latest, False
                previous = self.transcript.entries if self.transcript.key == data['id'] else []
                messages = [dict(role=entry['role'], status=entry['status'], content=entry['content'])
                            for entry in data['messages']]
                entries = await asyncio.to_thread(transcript_entries, messages, tuple(previous))
                if not self.active_host:
                    return
                if generation != self.transcript.generation or self.state.current is not data:
                    rendered = -1
                    continue
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
                    if rendered == self.transcript.revision:
                        self.transcript.ready = False
                        return
                elif generation == self.transcript.generation:
                    self.transcript.key, self.transcript.entries = data['id'], entries
        except (RuntimeError, ValueError) as error:
            self.set_chat_status('Conversation display unavailable: ' + str(error)[:200])

    async def chat_primary_action(self, widget=None, **kwargs):
        if self.state.busy:
            if self.state.generating:
                self.cancel_chat()
        else:
            await self.send_chat()

    def set_chat_busy(self, busy, *, generating=False):
        self.state.busy = busy
        self.state.generating = busy and generating
        for control in (self.chat_url, self.chat_key, self.chat_model, self.chat_models, self.chat_selector,
                        self.chat_new, self.chat_header_new, self.chat_refresh, self.chat_export, self.chat_actions_button,
                        self.chat_context, self.chat_max_tokens):
            control.enabled = not busy
        self.presentation.apply_icon(self.chat_send, 'stop' if self.state.generating else 'up',
                   'Stop' if self.state.generating else 'Send')
        self.presentation.surface(self.chat_send, radius=24, background='chat_primary', foreground='chat_on_primary', outlined=False)
        self.update_chat_readiness()
        self.chat_conversation_list.enabled = not busy
        if not busy and self.state.needs_initial_selection:
            # Initial discovery can finish while Connect owns the controls.
            # Complete selection once idle instead of dropping it when the
            # guarded new/open actions decline to run during that request.
            self.refresh_chats()

    def chat_fields(self):
        settings = dict(self.chat_profile['settings'], context_tokens=int(self.chat_context.value),
                        max_tokens=int(self.chat_max_tokens.value))
        validate_settings(settings)
        profile = dict(schema=1, base_url=self.chat_url.value.strip(), model=self.chat_model.value.strip(), settings=settings)
        self.chat_profile, self.chat_profile_original = self.chat_store.save_profile(profile, self.chat_profile_original)
        self.chat_url.value = self.chat_profile['base_url']
        return self.chat_profile

    def select_chat_model(self, widget, **kwargs):
        if not self.state.loading and widget.value:
            self.chat_model.value = widget.value

    async def refresh_chat_models(self, widget=None, **kwargs):
        if not self.app.require_feature('lm', destination='chat'):
            return
        if self.state.busy:
            return
        self.set_chat_busy(True)
        self.set_chat_status('Connecting to server…')
        try:
            profile = self.chat_fields()
            self.state.client = ChatClient(profile['base_url'], self.chat_key.value)
            models = await asyncio.to_thread(self.state.client.models)
            # Replacing Selection.items can fire on_change for its first item.
            # Retain the configured/manual model if the server still offers it.
            selected = profile['model'] if profile['model'] in models else (models[0] if models else '')
            self.state.loading = True
            try:
                self.chat_models.items = models
                if selected:
                    self.chat_models.value = selected
            finally:
                self.state.loading = False
            if models:
                self.chat_model.value = selected
                self.chat_fields()
            self.set_chat_status(f'Connected. {len(models)} model(s) available. Save & return to chat.' if models
                                 else 'Connected, but no models were listed. Load a model on the server or enter its exact ID below.')
        except Exception as error:
            self.set_chat_status('Models unavailable: ' + str(error)[:400])
        finally:
            self.state.client = None
            self.set_chat_busy(False)

    async def send_chat(self, widget=None, **kwargs):
        if not self.app.require_feature('lm', destination='chat'):
            return
        if self.state.busy or self.state.current is None:
            return
        prompt = self.chat_prompt.value.strip()
        if not prompt:
            self.set_chat_status('Enter a message first.')
            return
        if len(self.state.current['messages']) > 198:
            self.set_chat_status('This conversation has reached 200 messages. Start a new conversation.')
            return
        self.set_chat_busy(True, generating=True)
        self.state.cancelled = False
        session = None
        transport = None
        response = None
        before = None
        try:
            from features.lm.session import ConversationSession
            from features.lm.generation import GenerationCoordinator, GenerationInputs
            from features.lm.execution.mobile import MobileGenerationTransport
            profile = self.chat_fields()
            data = self.state.current
            session = ConversationSession(self.chat_store)
            session.attach(data)
            before = session.append_user(prompt, settings=profile['settings'], model=profile['model'],
                                         title_limit=60, retitle=True)
            self.state.client = ChatClient(profile['base_url'], self.chat_key.value)
            transport = MobileGenerationTransport(self.state.client, session,
                current=lambda: self.active_host and self.state.current is data)
            coordinator = GenerationCoordinator(session, transport)
            try:
                plan = coordinator.prepare(GenerationInputs(profile))
            except Exception:
                session.rollback(before)
                raise
            def published():
                self.state.loading = True
                self.chat_prompt.value = ''
                self.state.loading = False
                self.resize_chat_composer()
                self.transcript.force_latest = True
                self.update_chat_transcript()
            try:
                result = coordinator.start(plan, self.chat_key.value, clear_draft=True, published=published)
            except (OSError, ValueError):
                session.rollback(before)
                self.state.loading = True
                self.chat_prompt.value = data['draft']
                self.state.loading = False
                raise ValueError('The request was not sent because its recovery record could not be saved.')
            if not result.started:
                raise ValueError(result.error)
            response = session.response_token
            assistant = session.active_message
            omitted = plan.metadata['omitted_turns']
            self.set_chat_status(f'Generating… {omitted} older turn(s) omitted from context.' if omitted else 'Generating…')
            reason = await transport.drain(changed=self.update_chat_transcript, checkpoint=self.checkpoint_chat)
            session.complete_response('cancelled' if self.state.cancelled else 'complete', '',
                                      dict(finish_reason=reason), token=response)
            assistant['finish_reason'] = reason
            self.set_chat_status('Reply stopped; partial text preserved.' if self.state.cancelled else '')
        except ChatCancelled:
            if session is not None:
                session.complete_response('cancelled', '', {}, token=response)
            self.set_chat_status('Request cancelled; partial text preserved.')
        except asyncio.CancelledError:
            if session is not None:
                session.complete_response('interrupted', '', {}, token=response)
            raise
        except Exception as error:
            if session is not None:
                session.complete_response('failed', str(error)[:400], {}, token=response)
            self.set_chat_status('Chat failed: ' + str(error)[:400])
        finally:
            self.state.loading = False
            if transport is not None:
                await transport.retire()
            elif self.state.client:
                self.state.client.cancel()
            self.state.client = None
            self.checkpoint_chat()
            self.update_chat_transcript()
            self.refresh_chats()
            self.set_chat_busy(False)

    def cancel_chat(self, widget=None, **kwargs):
        self.state.cancelled = True
        if self.state.client:
            self.state.client.cancel()
        self.chat_send.enabled = False
        self.set_chat_status('Stopping…')

    async def export_chat(self, widget=None, **kwargs):
        if self.state.busy or self.state.current is None:
            return
        try:
            content = export_chat(self.state.current).encode('utf-8')
            done = await self.presentation.export_document(self, 'Conversation.md', content)
            self.set_chat_status('Conversation exported.' if done else 'Export cancelled.')
        except Exception as error:
            self.set_chat_status('Export failed: ' + str(error)[:400])
