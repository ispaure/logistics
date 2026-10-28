"""Named feature effects at the host privacy boundary; no permission decisions."""


def retire_stale_content(app):
    """Retire revoked sources; dirty drafts retain their own protected lifetime."""
    output = getattr(app, 'audio_output', None)
    if output is not None:
        output.invalidate()
    video = getattr(app, 'video_player', None)
    if video is not None:
        video.retire_stale()
    from features.notebooks.mobile.documents import retire_stale_notebooks
    retire_stale_notebooks(app)
    app.credential_document_lists.refresh()
    app.retire_private_comic_batch(stale_only=True)
    private = getattr(app, 'private_sessions', None)
    if private is not None:
        private.revoke_stale()
    if hasattr(app, 'cloud_view'):
        app.clear_private_catalog()
        app.cloud_rows = {}
        app.cloud_entries.items = []
        app.cloud_open_remote = None
        app.cloud_location.value = app.cloud_path = ''
    app.refresh_folder_actions()
    from features.books.mobile.media_controls import enforce_privacy
    enforce_privacy(app)
