"""Application shutdown decisions and disposable-resource lifetime.

The host supplies session, privacy, checkpoint and cancellation services. Keep this
order stable: a veto must leave the active document and native controls usable.
"""

def exit_app(self, app, **kwargs):
    if getattr(self, '_startup_in_progress', False):
        pending = getattr(self, 'startup_task', None)
        if pending is not None:
            pending.cancel()
        self.active_host = False
        return True
    if getattr(self, '_reset_scheduled', False):
        return True
    self.retire_private_comic_batch()
    background = getattr(self, 'cloud_startup_task', None)
    restoring = background is not None and not background.done()
    if getattr(self, 'cloud_busy', False) and not restoring:
        self.cancel_cloud()
        return False
    if getattr(self, 'private_sessions', None) is not None:
        if not self.clear_private_reader():
            return False
    if getattr(self, 'cloud_client', None):
        self.cloud_client.cancel()
    if getattr(self, 'chat_client', None):
        self.chat_client.cancel()
    if hasattr(self, 'chat_current') and not self.checkpoint_chat():
        return False
    saved = self.checkpoint()
    if saved:
        if restoring:
            self.active_host = False
            background.cancel()
        from .markdown_speech import stop_markdown_speech
        stop_markdown_speech(self)
        from features.books.mobile.media_controls import stop_media
        stop_media(self)
        vault = getattr(self, 'vault_browser', None)
        if vault is not None:
            vault.dispose()
        picker = getattr(self, '_editor_picker', None)
        if picker is not None:
            picker.clear()
        self.memory_pressure.dispose()
        self.screen_privacy.dispose()
        self.seasonal_snow.dispose()
    return saved


def release_disposable_resources(self):
    if not self.active_host:
        return
    from .markdown_speech import stop_markdown_speech
    from features.books.mobile.media_controls import current_panel
    playing = current_panel(self)
    stop_markdown_speech(self, keep=playing)
    self.retire_private_comic_batch()
    private = getattr(self, 'private_sessions', None)
    if private is not None:
        keep = next((owner for owner in private.controllers.values()
            if (getattr(getattr(owner, 'provider_epub_view', None), 'speech_panel', None) is playing
                or getattr(getattr(owner, 'markdown_speech', None), 'panel', None) is playing)
            and playing is not None), None)
        private.suspend(except_owner=keep, keep_active_markdown=True)
    readers = getattr(self, 'readers', None)
    if readers is not None:
        for owner in readers.controllers.values():
            if playing is None or getattr(owner, 'speech_panel', None) is not playing:
                owner.suspend()
    for name in ('file_browser', 'remote_browser', 'editor_browser'):
        browser = getattr(self, name, None)
        if browser is not None:
            browser.icons.clear()
            decoded = getattr(browser, '_decoded_thumbnails', None)
            if decoded is not None:
                decoded.clear()


