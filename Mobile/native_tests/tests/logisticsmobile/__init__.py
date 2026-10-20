CASES = ('native_hub', 'native_navigation_foundation', 'native_route_back', 'native_preferences', 'native_documents', 'native_text_workspace', 'native_markdown_preview',
         'native_epub_reader', 'native_bookmarks', 'native_comic_fullscreen_reentry', 'native_reader_presentation', 'native_comic_reader', 'native_independent_windows', 'native_lm_chat', 'native_remote_preview_only', 'native_files_pins_and_reviewed_pulls', 'native_background_local_pull_push', 'native_rclone_files', 'native_secure_credentials',
         'native_credential_visibility', 'native_obsidian_vault', 'native_localcrypt_reading', 'native_localcrypt_resume_password_lock', 'native_localcrypt_snapshot_shield', 'native_private_workspace', 'native_localcrypt_text_editing',
         'native_localcrypt_metadata', 'native_localcrypt_failure_and_lock', 'native_localcrypt_read_during_download', 'native_localcrypt_folder_pull_push', 'native_shared_transfer_reviews', 'native_localcrypt_file_management', 'native_rotation_safe_areas')


def start_native_check(app, exercise):
    """Activity recreation can repeat on_running before a queued check starts."""
    task = getattr(app, '_native_check_task', None)
    if task is None:
        task = app.loop.create_task(exercise(app))
        app._native_check_task = task
    return task
