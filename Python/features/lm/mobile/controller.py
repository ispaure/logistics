"""Owned workflow state and explicit application services."""
from services.workflow_host import HostAttribute
from features.lm.mobile.ui import ChatUI


class ChatController(ChatUI):
    METHODS = ('show_chat', 'toggle_chat_conversations', 'render_chat_workspace', 'update_chat_readiness', 'sync_chat_navigation', 'reserve_chat_navigation', 'update_chat_header', 'resize_chat_composer', 'sync_chat_appearance', 'set_chat_status', 'show_chat_actions', 'new_chat_from_actions', 'invoke_chat_action', 'show_chat_messages', 'show_chat_configuration', 'save_chat_configuration', 'refresh_chats', 'checkpoint_chat', 'open_chat', 'select_chat', 'new_chat', 'chat_draft_changed', 'update_chat_transcript', 'chat_transcript_loaded', 'schedule_chat_render', 'render_chat_transcript', 'chat_primary_action', 'set_chat_busy', 'chat_fields', 'select_chat_model', 'refresh_chat_models', 'send_chat', 'cancel_chat', 'export_chat')
    FIELDS = ('chat_actions', 'chat_actions_button', 'chat_bar_appearance', 'chat_busy', 'chat_cancelled', 'chat_client', 'chat_composer', 'chat_config_status', 'chat_config_status_box', 'chat_config_view', 'chat_context', 'chat_conversation_buttons', 'chat_conversation_list', 'chat_current', 'chat_drawer_open', 'chat_drawer_settings', 'chat_export', 'chat_force_latest', 'chat_generating', 'chat_header', 'chat_header_actions', 'chat_header_new', 'chat_key', 'chat_labels', 'chat_loading', 'chat_max_tokens', 'chat_menu_button', 'chat_messages', 'chat_model', 'chat_model_label', 'chat_models', 'chat_native_menu', 'chat_new', 'chat_profile', 'chat_profile_original', 'chat_prompt', 'chat_refresh', 'chat_render_entries', 'chat_render_generation', 'chat_render_key', 'chat_render_ready', 'chat_render_revision', 'chat_render_task', 'chat_selector', 'chat_send', 'chat_setup', 'chat_setup_box', 'chat_sidebar', 'chat_sidebar_content', 'chat_sidebar_title', 'chat_status', 'chat_status_box', 'chat_store', 'chat_title', 'chat_transcript', 'chat_transcript_card', 'chat_url', 'chat_view', 'chat_workspace')

    def __init__(self, app):
        self.app = app

    _impl = HostAttribute('_impl')
    active_host = HostAttribute('active_host')
    adaptive = HostAttribute('adaptive')
    loop = HostAttribute('loop')
    main_window = HostAttribute('main_window')
    native_host = HostAttribute('native_host')
    preferences = HostAttribute('preferences')
    private_root = HostAttribute('private_root')
    routes = HostAttribute('routes')
    show_view = HostAttribute('show_view')
