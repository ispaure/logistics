"""The retained Chat settings panel opened from Chat or app Settings."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from commonUtils.ui.native.adaptive import allocated_width
from commonUtils.ui.native.appearance import accessible_name
from commonUtils.ui.native.forms import FittedLabel, fit_section, group_rows
from commonUtils.ui.native.password_input import PasswordInput

from .on_device import MODELS, PROVIDERS, platform_provider


class ChatSettingsPanel:
    """Build and present settings with the Chat controller's state and callbacks."""

    def _build_chat_connection_controls(self):
        self.chat_url = toga.TextInput(value=self.chat_profile['base_url'],
            placeholder='e.g. http://192.168.1.10:1234', style=Pack(height=48))
        self.chat_key = PasswordInput(placeholder='API key (session only)', style=Pack(height=48))
        self.chat_model = toga.TextInput(value=self.chat_profile['model'], placeholder='Exact model ID', style=Pack(height=48))
        self.chat_models = toga.Selection(on_change=self.select_chat_model, style=Pack(height=48))
        self.chat_refresh = toga.Button('Connect & load models', on_press=self.refresh_chat_models, style=Pack(height=48))

    def _build_chat_configuration(self):
        """Build session-key and generation settings without contacting the server."""
        provider = self.chat_profile.get('provider', 'server')
        choices = ['OpenAI-compatible server']
        local = platform_provider()
        if local:
            choices.append(MODELS[local])
        if provider in MODELS and MODELS[provider] not in choices:
            choices.append(MODELS[provider])
        self._selected_chat_provider = provider
        self.chat_provider = toga.Selection(items=choices,
            value=MODELS.get(provider, choices[0]), on_change=self.select_chat_provider, style=Pack(height=48))
        contexts = sorted({'2048', '3072', '4096', '8192', '16384', '32768', str(self.chat_profile['settings']['context_tokens'])}, key=int)
        replies = sorted({'256', '512', '1024', '2048', '4096', str(self.chat_profile['settings']['max_tokens'])}, key=int)
        self.chat_context = toga.Selection(items=contexts,
            value=str(self.chat_profile['settings']['context_tokens']), style=Pack(height=48))
        self.chat_max_tokens = toga.Selection(items=replies,
            value=str(self.chat_profile['settings']['max_tokens']), style=Pack(height=48))
        self.chat_status = toga.MultilineTextInput(readonly=True, style=Pack(height=48, font_size=12))
        self.chat_config_status = toga.MultilineTextInput(readonly=True, style=Pack(height=48, font_size=12))
        self.chat_config_status_box = toga.Box(style=Pack(direction=COLUMN))
        def label(text, *, heading=False, field=False):
            control = FittedLabel(text, style=Pack(font_size=16 if heading else 14 if field else 12,
                font_weight='bold' if heading else 'normal', margin_top=12 if heading else 4))
            return self.presentation.surface(control, radius=0,
                foreground='text' if heading or field else 'muted', background='transparent', outlined=False, eink_outlined=False)

        def field(text, control, help_text=None):
            accessible_name(control, text)
            children = [label(text, field=True), control]
            if help_text:
                children.append(label(help_text))
            return toga.Box(children=children, style=Pack(direction=COLUMN, gap=4, margin_top=4, margin_bottom=8))

        def group(*rows):
            return group_rows(rows, surface=self.presentation.surface,
                              background='settings_group', separator='settings_separator')

        self.chat_config_back = toga.Button('Back', on_press=lambda widget, **kw: self.routes.back(), style=Pack(height=48))
        self.chat_config_save = self.presentation.action_button(toga.Button('Save settings',
            on_press=self.save_chat_configuration, style=Pack(height=48)))
        self.chat_server_section = toga.Box(children=[label('Connection', heading=True), group(
            field('Server address', self.chat_url, 'Enter the server’s address and port. /v1 is added automatically.'),
            field('API key (optional)', self.chat_key, 'The key is kept for this app session.'),
        )], style=Pack(direction=COLUMN, gap=8))
        self.chat_device_note = label('')
        self.chat_device_section = toga.Box(children=[label('On-device model', heading=True), self.chat_device_note],
                                              style=Pack(direction=COLUMN, gap=8))
        self.chat_connection_feedback = toga.Box(children=[self.chat_refresh, self.chat_config_status_box],
            style=Pack(direction=COLUMN))
        self.chat_connection_actions = group(self.chat_connection_feedback)
        self.chat_save_feedback = toga.Box(style=Pack(direction=COLUMN))
        self.chat_manual_box = toga.Box(style=Pack(direction=COLUMN))
        self.chat_manual_toggle = toga.Button('Enter model ID manually',
            on_press=self.toggle_chat_manual_model, style=Pack(height=48))
        if self.chat_profile.get('provider', 'server') == 'server' and self.chat_model.value:
            self.chat_manual_box.add(self.chat_model)
            self.chat_manual_toggle.text = 'Hide manual model ID'
        self.chat_model_choices = toga.Box(style=Pack(direction=COLUMN))
        self.chat_model_hint = label('Connect to load available models, or enter a model ID.')
        self.chat_generation_box = toga.Box(style=Pack(direction=COLUMN))
        self.chat_generation_fields = toga.Box(children=[group(
            field('Context tokens', self.chat_context, 'Limits how much conversation history is sent.'),
            field('Maximum reply tokens', self.chat_max_tokens, 'Limits the length of each reply.'),
        )], style=Pack(direction=COLUMN))
        self.chat_generation_toggle = toga.Button('Generation limits…',
            on_press=self.toggle_chat_generation, style=Pack(height=48))
        self.chat_model_section = toga.Box(children=[label('Model', heading=True),
            group(self.chat_model_choices, self.chat_manual_toggle, self.chat_manual_box),
            label('Generation', heading=True), self.chat_generation_toggle, self.chat_generation_box],
            style=Pack(direction=COLUMN, gap=6))
        accessible_name(self.chat_models, 'Available models')
        accessible_name(self.chat_model, 'Exact model ID')
        self.chat_provider_content = toga.Box(style=Pack(direction=COLUMN, gap=8))
        self.chat_config_content = toga.Box(style=Pack(direction=COLUMN, margin=16, gap=8))
        self.chat_config_title = label('Chat settings', heading=True)
        self.chat_config_title.style.margin_top = 0
        self.chat_config_title._settings_page_title = 'Chat settings'
        if not self.routes.apple:
            self.chat_config_content.add(self.chat_config_back, self.chat_config_title)
        if len(choices) > 1:
            self.chat_config_content.add(label('Provider', heading=True), group(field('Model provider', self.chat_provider)))
        self.chat_config_content.add(self.chat_provider_content, self.chat_save_feedback, self.chat_config_save)
        self.chat_config_view = toga.ScrollContainer(horizontal=False,
            content=self.chat_config_content, style=Pack(flex=1))
        for surface in (self.chat_config_view, self.chat_config_content):
            self.presentation.surface(surface, radius=0, background='settings_background',
                                      outlined=False, eink_outlined=False)
        self.presentation.register_layout('chat-settings', self, ChatSettingsPanel.fit_chat_configuration)

        self.select_chat_provider()

    def show_chat_configuration(self, widget=None, *, destination=None, **kwargs):
        if not self.active_host:
            return
        destination = destination or ('settings' if self.native_host.state.destination == 'settings' else 'chat')
        if not self.app.require_feature('lm', destination=destination):
            return
        if not hasattr(self, 'chat_store'):
            self.show_chat(present=False)
        self.chat_config_destination = destination
        self.chat_config_back.text = 'Back to LM Chat' if destination == 'settings' else 'Back to conversation'
        if self.routes.apple:
            title = self.chat_config_title
            if destination == 'settings' and title.parent is None:
                self.chat_config_content.insert(0, title)
            elif destination != 'settings' and title.parent is self.chat_config_content:
                self.chat_config_content.remove(title)
        self.show_view(self.chat_config_view, destination=destination, route='chat-settings', title='Chat settings')
        self.fit_chat_configuration()

    def fit_chat_configuration(self, frame=None):
        destination = getattr(self, 'chat_config_destination', 'chat')
        fallback = self.adaptive.content_width(destination, margin=0)
        width = allocated_width(self.chat_config_view, fallback)
        inset = max(16, (int(width) - 680) // 2)
        self.chat_config_content.style.margin_left = self.chat_config_content.style.margin_right = inset
        fit_section(self.chat_config_content, max(1, width))

    def toggle_chat_manual_model(self, widget=None, **kwargs):
        if self.chat_model in self.chat_manual_box.children:
            self.chat_manual_box.remove(self.chat_model)
            self.chat_manual_toggle.text = 'Enter model ID manually'
        else:
            self.chat_manual_box.add(self.chat_model)
            self.chat_manual_toggle.text = 'Hide manual model ID'
        self.fit_chat_configuration()

    def toggle_chat_generation(self, widget=None, **kwargs):
        if self.chat_generation_fields in self.chat_generation_box.children:
            self.chat_generation_box.remove(self.chat_generation_fields)
            self.chat_generation_toggle.text = 'Generation limits…'
        else:
            self.chat_generation_box.add(self.chat_generation_fields)
            self.chat_generation_toggle.text = 'Hide generation limits'
        self.fit_chat_configuration()

    def select_chat_provider(self, widget=None, **kwargs):
        if not hasattr(self, 'chat_context') or self.state.busy:
            return
        provider = PROVIDERS[self.chat_provider.value]
        server = provider == 'server'
        for control in (self.chat_url, self.chat_key, self.chat_models, self.chat_model, self.chat_context, self.chat_max_tokens):
            control.enabled = server
        self.chat_refresh.text = ('Connect & load models' if server else
                                  'Prepare Gemini Nano (may download)' if provider == 'nano' else
                                  'Check on-device availability')
        self.chat_config_save.enabled = not self.state.busy
        content = [self.chat_server_section if server else self.chat_device_section, self.chat_connection_actions]
        self.chat_device_note.text = ('Uses the system model. Preparation may download model assets.' if provider == 'nano'
                                      else 'Uses Apple Intelligence. Requires a supported device and a ready system model.')
        if server:
            content.append(self.chat_model_section)
        if list(self.chat_provider_content.children) != content:
            for child in list(self.chat_provider_content.children):
                self.chat_provider_content.remove(child)
            self.chat_provider_content.add(*content)
        changed = provider != self._selected_chat_provider
        previous = self._selected_chat_provider
        self._selected_chat_provider = provider
        if changed:
            if previous == 'server':
                self._chat_server_model = (self.chat_model.value, [row.value for row in self.chat_models.items])
            saved_model, saved_models = getattr(self, '_chat_server_model', ('', [])) if server else ('', [])
            self.chat_model.value = saved_model
            self.state.loading = True
            try:
                self.chat_models.items = saved_models
                if saved_model in saved_models:
                    self.chat_models.value = saved_model
            finally:
                self.state.loading = False
            self.set_chat_status('')
        model_choice = self.chat_models if self.chat_models.items else self.chat_model_hint
        if list(self.chat_model_choices.children) != [model_choice]:
            for child in list(self.chat_model_choices.children):
                self.chat_model_choices.remove(child)
            self.chat_model_choices.add(model_choice)
        self.fit_chat_configuration()
