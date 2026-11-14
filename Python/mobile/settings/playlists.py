"""Confirmed playlist deletion without opening or deleting source notes."""

import asyncio

import toga
from toga.style import Pack

from features.notes_library.playlists import PlaylistStore
from mobile.favourites import unlocked_ciphers
from services.documents.authoring.document_dialogs import DocumentDialog, DocumentTypeDialog

from .forms import SettingsLabel


def dismiss_playlist_dialog(app):
    task = getattr(app, '_playlist_settings_dialog', None)
    if task is not None and not task.done():
        task.cancel()


def controls(app, box):
    def current():
        privacy = getattr(app, 'screen_privacy', None)
        return (app.active_host and app.native_host.state.destination == 'settings'
                and (privacy is None or not (privacy.inactive or privacy.captured or privacy.resume_locked)))

    async def choose(dialog):
        task = app.loop.create_task(app.main_window.dialog(dialog))
        app._playlist_settings_dialog = task
        try:
            return await task
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            return None
        finally:
            if app._playlist_settings_dialog is task:
                app._playlist_settings_dialog = None

    async def failed():
        if current():
            await app.main_window.dialog(toga.InfoDialog(
                'Could not update playlists', 'Check storage access and try again.'))

    async def delete(widget, **kwargs):
        if not current():
            return
        widget.enabled = False
        try:
            store = PlaylistStore(app.private_root, app=app)
            records = await asyncio.to_thread(store.all, ciphers=tuple(unlocked_ciphers(app)))
            if not current():
                return
            if not records:
                await app.main_window.dialog(toga.InfoDialog('Delete playlist',
                    'There are no available playlists. Unlock protected storage to see its saved playlists.'))
                return
            dialog = DocumentTypeDialog(choices=[
                (record.name + (' · This session' if record.session_only else ''), record.id)
                for record in records])
            dialog.title, dialog.message = 'Delete playlist', 'Choose a playlist to review before deleting.'
            identity = await choose(dialog)
            record = next((row for row in records if row.id == identity), None)
            if record is None or not current():
                return
            confirmation = DocumentDialog('Delete playlist?',
                f'Delete “{record.name}” and its saved position? The source notes will be kept.', delete=True)
            if await choose(confirmation) == 'delete' and current():
                await asyncio.to_thread(store.delete_record, record, ciphers=tuple(unlocked_ciphers(app)))
        except (OSError, ValueError):
            await failed()
        finally:
            widget.enabled = True

    async def clear(widget, **kwargs):
        if not current():
            return
        widget.enabled = False
        try:
            store = PlaylistStore(app.private_root, app=app)
            count = await asyncio.to_thread(store.locked_count, ciphers=tuple(unlocked_ciphers(app)))
            if not current():
                return
            if count == 0:
                await app.main_window.dialog(toga.InfoDialog('Clear locked playlists',
                    'There are no locked playlist records.'))
                return
            if await app.main_window.dialog(toga.ConfirmDialog('Clear locked playlists?',
                'Delete playlist records whose credentials are locked or unreadable? The source notes will be kept.'
            )) and current():
                await asyncio.to_thread(store.clear_locked, ciphers=tuple(unlocked_ciphers(app)))
        except (OSError, ValueError):
            await failed()
        finally:
            widget.enabled = True

    box.add(SettingsLabel('Notes Library playlists', style=Pack(font_weight='bold', margin_top=16)))
    for label, handler, description in (
        ('Delete a playlist…', delete,
         'Choose a playlist to delete along with its saved playback position. Source notes are kept. Unlock protected storage to list its playlists.'),
        ('Clear locked playlists…', clear,
         'Delete playlist records whose credentials are locked or unreadable. Source notes and currently readable playlists are kept.'),
    ):
        button = toga.Button(label, on_press=handler, style=Pack(height=48))
        button._settings_destructive = True
        box.add(button, SettingsLabel(description))
