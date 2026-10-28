"""Owned workflow state and explicit application services."""

from __future__ import annotations

from asyncio import Task
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from services.workflow_host import HostService, StateAttribute
from features.lm.mobile.ui import ChatUI

if TYPE_CHECKING:
    from features.lm.mobile.transport import ChatClient


@dataclass
class ChatState:
    """Conversation/request state; controls and stored records keep their owners."""
    current: dict | None = None
    busy: bool = False
    loading: bool = False
    generating: bool = False
    cancelled: bool = False
    client: ChatClient | None = None
    inventory_task: Task | None = None
    inventory_again: bool = False
    needs_initial_selection: bool = False


@dataclass
class TranscriptState:
    """One WebView's publication epoch, pending render and incremental baseline."""
    ready: bool = False
    revision: int = 0
    generation: int = 0
    task: Task | None = None
    key: str | None = None
    entries: list[dict[str, str]] = field(default_factory=list)
    force_latest: bool = False


class ChatController(ChatUI):
    METHODS = (
        "show_chat",
        "toggle_chat_conversations",
        "render_chat_workspace",
        "update_chat_readiness",
        "sync_chat_navigation",
        "reserve_chat_navigation",
        "update_chat_header",
        "resize_chat_composer",
        "sync_chat_appearance",
        "set_chat_status",
        "show_chat_actions",
        "new_chat_from_actions",
        "invoke_chat_action",
        "show_chat_messages",
        "show_chat_configuration",
        "save_chat_configuration",
        "refresh_chats",
        "checkpoint_chat",
        "open_chat",
        "select_chat",
        "new_chat",
        "chat_draft_changed",
        "update_chat_transcript",
        "chat_transcript_loaded",
        "schedule_chat_render",
        "render_chat_transcript",
        "chat_primary_action",
        "set_chat_busy",
        "chat_fields",
        "select_chat_provider",
        "select_chat_model",
        "refresh_chat_models",
        "send_chat",
        "cancel_chat",
        "export_chat",
    )
    FIELDS = (
        "chat_actions",
        "chat_actions_button",
        "chat_bar_appearance",
        "chat_busy",
        "chat_cancelled",
        "chat_client",
        "chat_composer",
        "chat_config_status",
        "chat_config_status_box",
        "chat_config_view",
        "chat_context",
        "chat_conversation_buttons",
        "chat_conversation_list",
        "chat_current",
        "chat_drawer_open",
        "chat_drawer_settings",
        "chat_export",
        "chat_force_latest",
        "chat_generating",
        "chat_header",
        "chat_header_actions",
        "chat_header_new",
        "chat_key",
        "chat_labels",
        "chat_loading",
        "chat_max_tokens",
        "chat_menu_button",
        "chat_messages",
        "chat_model",
        "chat_model_label",
        "chat_models",
        "chat_native_menu",
        "chat_new",
        "chat_profile",
        "chat_profile_original",
        "chat_prompt",
        "chat_provider",
        "chat_refresh",
        "chat_render_entries",
        "chat_render_generation",
        "chat_render_key",
        "chat_render_ready",
        "chat_render_revision",
        "chat_render_task",
        "chat_selector",
        "chat_send",
        "chat_setup",
        "chat_setup_box",
        "chat_sidebar",
        "chat_sidebar_content",
        "chat_sidebar_title",
        "chat_status",
        "chat_status_box",
        "chat_store",
        "chat_title",
        "chat_transcript",
        "chat_transcript_card",
        "chat_url",
        "chat_view",
        "chat_workspace",
    )

    def __init__(self, app):
        self.app = app
        self.state = ChatState()
        self.transcript = TranscriptState()

    chat_current = StateAttribute("state", "current")
    chat_busy = StateAttribute("state", "busy")
    chat_loading = StateAttribute("state", "loading")
    chat_generating = StateAttribute("state", "generating")
    chat_cancelled = StateAttribute("state", "cancelled")
    chat_client = StateAttribute("state", "client")
    _chat_inventory_task = StateAttribute("state", "inventory_task")
    _chat_inventory_again = StateAttribute("state", "inventory_again")
    _chat_needs_initial_selection = StateAttribute("state", "needs_initial_selection")
    chat_render_ready = StateAttribute("transcript", "ready")
    chat_render_revision = StateAttribute("transcript", "revision")
    chat_render_generation = StateAttribute("transcript", "generation")
    chat_render_task = StateAttribute("transcript", "task")
    chat_render_key = StateAttribute("transcript", "key")
    chat_render_entries = StateAttribute("transcript", "entries")
    chat_force_latest = StateAttribute("transcript", "force_latest")

    _impl = HostService("_impl")
    active_host = HostService("active_host")
    adaptive = HostService("adaptive")
    loop = HostService("loop")
    main_window = HostService("main_window")
    native_host = HostService("native_host")
    preferences = HostService("preferences")
    private_root = HostService("private_root")
    routes = HostService("routes")
    show_view = HostService("show_view")
    presentation = HostService("presentation")
