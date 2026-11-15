"""Owned workflow state and explicit application services."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from services.worker_retirement import drain_worker
from services.workflow_host import HostService, StateAttribute
from features.lm.execution.mobile import MobileGenerationTransport
from features.lm.generation import GenerationCoordinator, GenerationInputs
from features.lm.mobile.on_device import MODELS, PROVIDERS
from features.lm.mobile.transport import ChatCancelled
from features.lm.mobile.ui import ChatUI
from features.lm.session import ConversationSession

if TYPE_CHECKING:
    from features.lm.mobile.on_device import OnDeviceClient
    from features.lm.mobile.transport import ChatClient


@dataclass
class ChatOperation:
    """Exclusive ownership of the controls and one request's client."""
    generating: bool = False
    client: ChatClient | OnDeviceClient | None = None
    stop_requested: bool = False


@dataclass
class ChatState:
    """Conversation/request state; controls and stored records keep their owners."""
    current: dict | None = None
    loading: bool = False
    operation: ChatOperation | None = None
    inventory_task: asyncio.Task | None = None
    inventory_again: bool = False
    needs_initial_selection: bool = False

    @property
    def busy(self):
        return self.operation is not None

    @busy.setter
    def busy(self, busy):
        # Keep the app's writable busy alias for a controls-only reservation.
        if busy and self.operation is None:
            self.operation = ChatOperation()
        elif not busy and self.operation is not None and self.operation.client is None:
            self.operation = None

    @property
    def generating(self):
        return self.operation is not None and self.operation.generating

    @property
    def cancelled(self):
        return self.operation is not None and self.operation.stop_requested

    @property
    def client(self):
        return self.operation.client if self.operation is not None else None


@dataclass
class TranscriptState:
    """One WebView's publication epoch, pending render and incremental baseline."""
    ready: bool = False
    revision: int = 0
    generation: int = 0
    task: asyncio.Task | None = None
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

    def set_chat_busy(self, busy, *, generating=False):
        self.state.busy = busy
        if busy and self.state.client is None:
            self.state.operation.generating = generating
        self._update_chat_operation_controls()

    def _finish_chat_operation(self, operation):
        if self.state.operation is operation:
            self.state.operation = None
            self._update_chat_operation_controls()

    def _chat_operation_current(self, operation):
        return self.active_host and self.state.operation is operation

    async def refresh_chat_models(self, widget=None, **kwargs):
        if not self.active_host:
            return
        if not self.app.require_feature('lm', destination=getattr(self, 'chat_config_destination', 'chat')):
            return
        if self.state.busy:
            return

        operation = ChatOperation()
        self.state.operation = operation
        try:
            self._update_chat_operation_controls()
            server = PROVIDERS[self.chat_provider.value] == 'server'
            self.set_chat_status('Connecting to server…' if server else 'Preparing on-device model…')
            profile = self.chat_fields()
            operation.client = self._chat_request_client(profile, self.chat_key.value)
            worker = asyncio.create_task(asyncio.to_thread(operation.client.models))
            try:
                models = await asyncio.shield(worker)
            except asyncio.CancelledError:
                operation.client.cancel()
                await drain_worker(worker)
                raise
            if self._chat_operation_current(operation):
                self._show_chat_models(profile, models)
        except Exception as error:
            if self._chat_operation_current(operation):
                self._show_chat_model_error(error)
        finally:
            self._finish_chat_operation(operation)

    async def send_chat(self, widget=None, **kwargs):
        if not self.active_host or not self.app.require_feature('lm', destination='chat'):
            return
        data = self.state.current
        if self.state.busy or data is None:
            return
        prompt = self.chat_prompt.value.strip()
        if not prompt:
            self.set_chat_status('Enter a message first.')
            return
        if len(data['messages']) > 198:
            self.set_chat_status('This conversation has reached 200 messages. Start a new conversation.')
            return

        session = ConversationSession(self.chat_store)
        session.attach(data)
        operation = ChatOperation(generating=True)
        self.state.operation = operation
        transport = response = None

        def current():
            return self._chat_operation_current(operation) and self.state.current is data

        def published():
            nonlocal response
            response = session.response_token
            if current():
                self._show_chat_pending_turn()

        try:
            self._update_chat_operation_controls()
            profile = self.chat_fields()
            api_key = self.chat_key.value
            # Client validation must not insert a turn into history.
            operation.client = self._chat_request_client(profile, api_key)
            transport = MobileGenerationTransport(operation.client, session, current=current)
            coordinator = GenerationCoordinator(session, transport)
            plan = self._start_chat_turn(coordinator, prompt, profile, api_key, published=published)
            assistant = session.active_message
            if current():
                omitted = plan.metadata['omitted_turns']
                self.set_chat_status(f'Generating… {omitted} older turn(s) omitted from context.' if omitted else 'Generating…')
            reason = await transport.drain(changed=self.update_chat_transcript,
                                           checkpoint=lambda: self._checkpoint_chat_record(data))
            stopped = operation.stop_requested
            if response is not None and session.complete_response('cancelled' if stopped else 'complete', '',
                                                                   dict(finish_reason=reason), token=response):
                assistant['finish_reason'] = reason
            if current():
                self.set_chat_status('Reply stopped; partial text preserved.' if stopped else '')
        except ChatCancelled:
            if response is not None:
                session.complete_response('cancelled', '', {}, token=response)
            if current():
                self.set_chat_status('Request cancelled; partial text preserved.')
        except asyncio.CancelledError:
            if response is not None:
                session.complete_response('interrupted', '', {}, token=response)
            raise
        except Exception as error:
            detail = str(error)[:400]
            if response is not None:
                session.complete_response('failed', detail, {}, token=response)
            if current():
                self.set_chat_status('Chat failed: ' + detail)
        finally:
            await self._retire_chat_generation(operation, transport, data, current=current)

    def _start_chat_turn(self, coordinator, prompt, profile, api_key, *, published):
        session = coordinator.session
        before = session.append_user(prompt, settings=profile['settings'], model=profile['model'],
                                     title_limit=60, retitle=True)
        provider = profile.get('provider')
        request_profile = dict(profile, base_url='on-device://' + provider) if provider in MODELS else profile
        try:
            plan = coordinator.prepare(GenerationInputs(request_profile))
        except Exception:
            session.rollback(before)
            raise
        try:
            result = coordinator.start(plan, api_key, clear_draft=True, published=published)
        except (OSError, ValueError) as error:
            session.rollback(before)
            if self.active_host:
                self._set_chat_draft(session.data['draft'])
            raise ValueError('The request was not sent because its recovery record could not be saved.') from error
        if not result.started:
            raise ValueError(result.error)
        return plan

    async def _retire_chat_generation(self, operation, transport, data, *, current):
        try:
            if transport is not None:
                retirement = asyncio.create_task(transport.retire())
                try:
                    await asyncio.shield(retirement)
                except asyncio.CancelledError:
                    await drain_worker(retirement)
                    raise
            elif operation.client is not None:
                operation.client.cancel()
        finally:
            try:
                # The captured record still owns the reply when its view retires.
                self._checkpoint_chat_record(data)
                if current():
                    self.update_chat_transcript()
                    self.refresh_chats()
            finally:
                self._finish_chat_operation(operation)

    def cancel_chat(self, widget=None, **kwargs):
        operation = self.state.operation
        if not self.active_host or operation is None or not operation.generating or operation.stop_requested:
            return
        operation.stop_requested = True
        if operation.client is not None:
            operation.client.cancel()
        self.chat_send.enabled = False
        self.set_chat_status('Stopping…')

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
    chat_keyboard_visible = HostService("chat_keyboard_visible")
    loop = HostService("loop")
    main_window = HostService("main_window")
    native_host = HostService("native_host")
    preferences = HostService("preferences")
    private_root = HostService("private_root")
    routes = HostService("routes")
    show_view = HostService("show_view")
    presentation = HostService("presentation")
