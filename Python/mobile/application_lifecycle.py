"""Application shutdown decisions and disposable-resource lifetime.

The host supplies session, privacy, checkpoint and cancellation services. Keep this
order stable: a veto must leave the active document and native controls usable.
"""

class HostLifecycle:
    """One owner for replacement, exit decisions and disposable memory."""

    def __init__(self, host):
        self.host = host
        self.replacement_prepared = False
        self.replaced = False
        self.exited = False

    def stop_local_searches(self):
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
        pending = getattr(host, 'startup_task', None)
        if pending is not None and not pending.done():
            pending.cancel()
        host.active_host = False
        self.stop_local_searches()
        self.replacement_prepared = True

    def retire_for_replacement(self):
        """Retire callbacks/resources once, after successful preservation."""
        if self.replaced:
            return
        self.prepare_replacement()
        host = self.host
        layout = getattr(host, '_layout_participants', None)
        if layout is not None:
            layout.dispose()
        from .markdown_speech import stop_markdown_speech
        video = getattr(host, 'video_player', None)
        if video is not None:
            video.retire()
        from features.books.mobile.media_controls import stop_media
        stop_markdown_speech(host)
        stop_media(host)
        for panel in getattr(host, '_notebook_views', {}).values():
            panel.dispose()
        for name in ('vault_browser', 'notebook_panel', 'memory_pressure', 'screen_privacy'):
            resource = getattr(host, name, None)
            if resource is not None:
                resource.dispose()
        background = getattr(host, 'cloud_startup_task', None)
        if background is not None:
            background.cancel()
        if getattr(host, 'cloud_client', None) is not None:
            host.cancel_cloud()
        picker = getattr(host, '_editor_picker', None)
        if picker is not None:
            picker.clear()
        workspace = getattr(host, 'workspace', None)
        for session in getattr(workspace, 'sessions', {}).values():
            workspace.invalidate(session.id)
        cancelled = getattr(host, '_crypt_cancel', None)
        if cancelled is not None:
            cancelled.set()
            client = getattr(host, 'cloud_client', None)
            if client is not None:
                client.cancel()
        # Activity recreation keeps the Python process alive. Retire the old
        # presentation explicitly; native destruction alone leaves Python
        # callbacks, Back delegates and scheduled effects attached to it.
        for view in tuple(getattr(host, 'text_views', {}).values()):
            view.dispose()
        for name in ('_keyboard_dismissal', 'seasonal_snow'):
            resource = getattr(host, name, None)
            if resource is not None:
                resource.dispose()
        for name in ('adaptive', 'routes'):
            resource = getattr(host, name, None)
            if resource is not None:
                resource.uninstall()
        navigation = getattr(host, 'native_host', None)
        if navigation is not None:
            navigation.dispose()
        self.replaced = True

    def request_exit(self):
        host = self.host
        if self.exited:
            return True
        if getattr(host, '_startup_in_progress', False):
            pending = getattr(host, 'startup_task', None)
            if pending is not None:
                pending.cancel()
            host.active_host = False
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
            if restoring:
                host.active_host = False
                background.cancel()
            from .markdown_speech import stop_markdown_speech
            video = getattr(host, 'video_player', None)
            if video is not None:
                video.retire()
            stop_markdown_speech(host)
            from features.books.mobile.media_controls import stop_media
            stop_media(host)
            for panel in getattr(host, '_notebook_views', {}).values():
                panel.dispose()
            vault = getattr(host, 'vault_browser', None)
            if vault is not None:
                vault.dispose()
            picker = getattr(host, '_editor_picker', None)
            if picker is not None:
                picker.clear()
            dismissal = getattr(host, '_keyboard_dismissal', None)
            if dismissal is not None:
                dismissal.dispose()
            host.memory_pressure.dispose()
            host.scene_manager.external_comics.dispose()
            host.screen_privacy.dispose()
            host.seasonal_snow.dispose()
        if saved:
            layout = getattr(host, '_layout_participants', None)
            if layout is not None:
                layout.dispose()
            self.stop_local_searches()
            self.exited = True
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
