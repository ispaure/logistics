"""Application shutdown decisions and disposable-resource lifetime.

The host supplies session, privacy, checkpoint and cancellation services. Keep this
order stable: a veto must leave the active document and native controls usable.
"""
import asyncio
import logging


logger = logging.getLogger(__name__)


class HostLifecycle:
    """One owner for replacement, exit decisions and disposable memory."""

    def __init__(self, host):
        self.host = host
        self.replacement_attempt = None
        self.replacement_prepared = False
        self.replaced = False
        self.exited = False
        self.startup_aborted = False
        self.secondary_retired = False
        self.secondary_retiring = False
        self.secondary_checkpoint_saved = None
        self._retired_actions = {}

    def _retire(self, resource, method):
        """Finish independent cleanup even if one native adapter fails.

        Successful actions run once; a later lifecycle notification can retry
        failed actions. Never include provider paths or exception text in logs.
        """
        if resource is None:
            return
        action = (id(resource), method)
        if action in self._retired_actions:
            return
        try:
            getattr(resource, method)()
        except Exception:
            logger.error('Host resource cleanup failed: %s.%s', type(resource).__name__, method)
        else:
            # Keep the disposed object with its identity until this host is
            # released; a later resource must never inherit a recycled id.
            self._retired_actions[action] = resource

    def _cancel_task(self, name):
        task = getattr(self.host, name, None)
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        # finish_startup also retires its host from inside its own exception
        # handler. Cancelling that task again interrupts failure presentation.
        if task is not current:
            self._retire(task, 'cancel')

    def stop_local_searches(self):
        from .notes_discovery import cancel
        cancel(self.host)
        for value in tuple(vars(self.host).values()):
            stop = getattr(type(value), 'stop_local_search', None)
            if stop is not None:
                stop(value)

    def prepare_replacement(self, receipt=None):
        """Preservation is a preflight; the predecessor stays active until claim."""
        from .session_workflows.transitions import transitions_for
        transitions_for(self.host).preserve_for_replacement(receipt)

    def retire_for_replacement(self, receipt=None, *, incoming=None, identity=None, attempt=None):
        """Admit once, claim before callbacks, then retry independent cleanup."""
        host = self.host
        private = getattr(host, 'private_sessions', None)
        if not self.replaced:
            readers = getattr(host, 'readers', None)
            if readers is not None:
                readers.require_replacement_safe()
            if private is not None and receipt is None:
                receipt = private.prepare_replacement_sync()
            self.prepare_replacement(receipt)
            # Preservation callbacks can reenter startup or mutate providers.
            if private is not getattr(host, 'private_sessions', None):
                raise OSError('The private workspace changed during replacement.')
            if private is not None:
                private.require_replacement_safe(receipt)
            # Provider access checks can reenter notebook commands too. Read the
            # retention state after the last such callback, before admission.
            from .session_workflows.transitions import transitions_for
            transitions_for(host).require_notebook_replacement_safe()
            if incoming is not None:
                from .app import _active_hosts
                own = lifecycle(incoming)
                if (self.replacement_attempt is not attempt or _active_hosts.get(identity) is not host
                        or own.replaced or own.startup_aborted):
                    raise asyncio.CancelledError
            # No await or arbitrary callback between the final checks and this
            # ownership change. Provider admission only sets terminal flags.
            if private is not None:
                private._admit_retirement()
            host.active_host = False
            self.replacement_prepared = self.replaced = True
            if incoming is not None:
                incoming.active_host = False
                incoming._startup_claim = identity
                _active_hosts[identity] = incoming
        if private is not None:
            self._retire(private, 'retire')
        self._retire_resources()

    def _release_startup_claim(self):
        """Forget this host without disturbing a successor's registration."""
        identity = self.host.__dict__.get('_startup_claim')
        if identity is not None:
            from .app import _active_hosts
            if _active_hosts.get(identity) is self.host:
                del _active_hosts[identity]

    def abort_startup(self):
        """Retire only initialized resources, without checkpointing partial state."""
        self.startup_aborted = True
        self._release_startup_claim()
        screen = getattr(self.host, 'startup_screen', None)
        self._retire(getattr(screen, 'cover', None), 'dispose')
        self._retire_resources()

    def retire_secondary_scene(self):
        """Preserve once, then retire a secondary scene the OS disconnected.

        Unlike voluntary close, destruction cannot be vetoed here. Keep the
        checkpoint result for recovery/diagnostics, without deleting sessions
        or clearing process credentials. Primary disconnect never calls this.
        """
        if self.secondary_retiring:
            return self.secondary_checkpoint_saved
        self.secondary_retiring = True
        try:
            first = not self.secondary_retired
            # Block reentrant/queued scene events even while checkpoint still
            # needs an active host. Teardown closes active_host immediately after.
            self.secondary_retired = True
            self._retire(self, '_cancel_scene_picker')
            try:
                if first:
                    self.secondary_checkpoint_saved = False
                    try:
                        self.secondary_checkpoint_saved = bool(self.host.checkpoint())
                    except Exception:
                        # A provider's exception may contain private paths or data.
                        pass
                    if not self.secondary_checkpoint_saved:
                        logger.error('Secondary scene checkpoint failed before terminal retirement')
            finally:
                self._retire_resources()
                self._retire(self, '_detach_scene_navigation')
        finally:
            self.secondary_retiring = False
        return self.secondary_checkpoint_saved

    def _cancel_scene_picker(self):
        from commonUtils.ui.native.documents import cancel_document_picker
        cancel_document_picker(self.host.main_window)

    def _detach_scene_navigation(self):
        navigation = getattr(self.host, 'navigation', None)
        if navigation is not None:
            try:
                navigation.window = None
            finally:
                navigation.app = None

    def _retire_resources(self):
        """Shared final teardown for exit, replacement and abandoned startup.

        Session save/close policy runs before this boundary. This method owns
        host tasks and presentation resources, never persistent document state.
        """
        host = self.host
        host.active_host = False
        for name in ('startup_task', 'startup_document_task', 'cloud_startup_task', 'incoming_task'):
            self._cancel_task(name)
        self._retire(self, 'stop_local_searches')
        self._retire(getattr(host, '_layout_participants', None), 'dispose')
        from .markdown_speech import stop_markdown_speech
        self._retire(getattr(host, 'video_player', None), 'retire')
        self._retire(getattr(host, 'readers', None), 'retire')
        from features.books.mobile.media_controls import stop_media
        self._stop_playback(stop_markdown_speech)
        self._stop_playback(stop_media)
        self._retire(getattr(host, '_transfer_controller', None), 'dispose')
        for panel in tuple(getattr(host, '_notebook_views', {}).values()):
            self._retire(panel, 'dispose')
        for name in ('vault_browser', 'notebook_panel', 'memory_pressure', 'screen_privacy', 'audio_output'):
            self._retire(getattr(host, name, None), 'dispose')
        if getattr(host, 'cloud_client', None) is not None:
            self._retire(host, 'cancel_cloud')
            self._retire(host.cloud_client, 'cancel')
        self._retire(getattr(host, 'chat_client', None), 'cancel')
        self._retire(getattr(host, '_editor_picker', None), 'clear')
        self._retire(self, '_invalidate_sessions')
        self._retire(getattr(host, '_crypt_cancel', None), 'set')
        # Activity recreation keeps the Python process alive. Retire the old
        # presentation explicitly; native destruction alone leaves Python
        # callbacks, Back delegates and scheduled effects attached to it.
        for view in tuple(getattr(host, 'text_views', {}).values()):
            self._retire(view, 'dispose')
        for name in ('_keyboard_dismissal', 'seasonal_snow'):
            self._retire(getattr(host, name, None), 'dispose')
        for name in ('adaptive', 'routes'):
            self._retire(getattr(host, name, None), 'uninstall')
        self._retire(getattr(host, 'native_host', None), 'dispose')
        # Android navigation restores its previous window resize handler while
        # disposing, so detach callbacks after the native adapter is retired.
        self._detach_window_callbacks()
        if self.exited:
            manager = getattr(host, 'scene_manager', None)
            self._retire(getattr(manager, 'external_comics', None), 'dispose')

    def _detach_window_callbacks(self):
        try:
            window = self.host.main_window
        except (AttributeError, ValueError):
            # Toga raises before startup assigns its main window.
            return
        if window is not None:
            try:
                window.on_lose_focus = None
                window.on_gain_focus = None
                window.on_resize = None
            except Exception:
                logger.error('Host window callback cleanup failed')

    def _invalidate_sessions(self):
        workspace = getattr(self.host, 'workspace', None)
        for session in tuple(getattr(workspace, 'sessions', {}).values()):
            workspace.invalidate(session.id)

    def _stop_playback(self, stop):
        if stop in self._retired_actions:
            return
        try:
            stop(self.host)
        except Exception:
            logger.error('Host playback cleanup failed')
        else:
            self._retired_actions[stop] = stop

    def request_exit(self):
        host = self.host
        if self.exited:
            self._release_startup_claim()
            self._retire_resources()
            return True
        if self.startup_aborted or getattr(host, '_startup_in_progress', False):
            self.abort_startup()
            return True
        if getattr(host, '_reset_scheduled', False):
            return True
        if any(panel.busy for panel in getattr(host, '_notebook_views', {}).values()) or getattr(getattr(host, 'notebook_panel', None), 'busy', False):
            return False
        for panel in getattr(host, '_notebook_views', {}).values():
            if panel.document is not None and panel.document.dirty and panel.document.recovery is None:
                from features.notebooks.mobile.documents import present
                present(host, panel)
                return False
        host.retire_private_comic_batch()
        background = getattr(host, 'cloud_startup_task', None)
        restoring = background is not None and not background.done()
        if getattr(host, 'cloud_busy', False) and not restoring:
            host.cancel_cloud()
            return False
        readers = getattr(host, 'readers', None)
        if readers is not None and (readers.flush_progress() or any(owner.book_busy for owner in readers.controllers.values())):
            return False
        if getattr(host, 'private_sessions', None) is not None:
            if not host.clear_private_reader():
                return False
        if getattr(host, 'cloud_client', None):
            host.cloud_client.cancel()
        if getattr(host, 'chat_client', None):
            host.chat_client.cancel()
        from .session_workflows.transitions import transitions_for
        saved = transitions_for(host).checkpoint_for_exit()
        if saved:
            self.exited = True
            # Preservation already succeeded. A later startup must not ask this
            # exited host's unavailable private manager to preserve it again.
            self._release_startup_claim()
            self._retire_resources()
        return saved

    def trim_memory(self):
        host = self.host
        if not host.active_host:
            return
        # Do not retain external bitmap references after the source is trimmed.
        from .external_display import sync as sync_external
        from .markdown_speech import stop_markdown_speech
        from features.books.mobile.media_controls import current_panel
        playing = current_panel(host)
        stop_markdown_speech(host, keep=playing)
        host.retire_private_comic_batch()
        private = getattr(host, 'private_sessions', None)
        if private is not None:
            keep = next((owner for owner in private.controllers.values()
                if (getattr(getattr(owner, 'provider_epub_view', None), 'speech_panel', None) is playing
                    or getattr(getattr(owner, 'markdown_speech', None), 'panel', None) is playing)
                and playing is not None), None)
            private.suspend(except_owner=keep, keep_active_markdown=True)
        readers = getattr(host, 'readers', None)
        if readers is not None:
            for owner in readers.controllers.values():
                if playing is None or getattr(owner, 'speech_panel', None) is not playing:
                    owner.suspend()
        for name in ('file_browser', 'remote_browser', 'editor_browser'):
            browser = getattr(host, name, None)
            if browser is not None:
                work = getattr(browser, 'work', None)
                if work is not None:
                    work.prune(set())
                else:
                    browser.icons.clear()
        # Android can dispatch its queued trim callback after Activity resume.
        # Recover only the currently visible, unlocked reader; hidden sessions stay trimmed.
        privacy = getattr(host, 'screen_privacy', None)
        if privacy is not None:
            privacy.resume_reader()
        sync_external(host)


def lifecycle(host):
    owner = host.__dict__.get('_host_lifecycle')
    if owner is None:
        owner = host._host_lifecycle = HostLifecycle(host)
    return owner


def exit_app(host, app, **kwargs):
    """Retain the native application callback signature."""
    return lifecycle(host).request_exit()


def release_disposable_resources(host):
    return lifecycle(host).trim_memory()
