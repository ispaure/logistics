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
        self.replacement_prepared = False
        self.replaced = False
        self.exited = False
        self.startup_aborted = False
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

    def prepare_replacement(self):
        """Flush durable state before replacement loads it on a worker thread."""
        if self.replacement_prepared:
            return
        host = self.host
        from .session_workflows.transitions import transitions_for
        transitions_for(host).preserve_for_replacement()
        self._cancel_task('startup_task')
        host.active_host = False
        self._retire(self, 'stop_local_searches')
        self.replacement_prepared = True

    def retire_for_replacement(self):
        """Retire callbacks/resources once, after successful preservation."""
        self.prepare_replacement()
        self._retire_resources()
        self.replaced = True

    def abort_startup(self):
        """Retire only initialized resources, without checkpointing partial state."""
        self.startup_aborted = True
        screen = getattr(self.host, 'startup_screen', None)
        self._retire(getattr(screen, 'cover', None), 'dispose')
        self._retire_resources()

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
