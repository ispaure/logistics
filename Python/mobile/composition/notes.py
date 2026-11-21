"""Bind the mobile app's services to the Notes Library and its drawers."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from functools import partial
from pathlib import Path


def notes_drawer_host(app):
    from features.notes_library.mobile.drawers import DrawerHost
    from ..appearance import surface
    from ..fold_layout import division
    from ..scroll_edges import sync_bottom
    from ..speech_overlay import SpeechOverlay

    def opening_blocked():
        privacy = getattr(app, 'screen_privacy', None)
        return privacy is not None and privacy.sensitive() and (
            privacy.inactive or privacy.interrupted or privacy.captured or privacy.resume_locked
        )

    return DrawerHost(
        loop=app.loop,
        window=lambda: app.main_window._impl.native,
        division=lambda view: division(app, view),
        overlay=lambda panel, owner, **options: SpeechOverlay(panel, owner, app, **options),
        surface=surface,
        sync_bottom=sync_bottom,
        opening_blocked=opening_blocked,
        eink=lambda: app.preferences.values.get('android_eink') == 'true',
    )


def notes_host(app):
    from commonUtils.ui.native.markdown_preview import MarkdownPreviewLimits
    from features.notes_library.mobile.notes_library import NotesHost
    from features.notes_library.notes import MAX_NOTE, MAX_RENDERED_HTML, MAX_IMAGE_HTML
    from services.documents.mobile_notebooks import notes_editor
    from services.documents.mobile_storage import NotesDocumentAccess
    from .. import obsidian
    from ..action_menu import FeatureCommands
    from ..appearance import accessible_name, batch_surfaces, list_button
    from ..audio_output import for_app
    from ..browser_ui import (
        FileBrowser, breadcrumb_separator, entry_icon, highlight_entry, middle_filename,
    )
    from ..favourites import relocate
    from ..folder_hub_style import source_tab
    from ..markdown_speech import MarkdownSpeech

    tree_rows = _tree_row_factory(app)
    timing_marker = Path(app.paths.cache) / 'notes-open-timing.enabled'
    preview_limits = MarkdownPreviewLimits(
        source_bytes=MAX_NOTE,
        html_bytes=MAX_RENDERED_HTML,
        image_html_bytes=MAX_IMAGE_HTML,
        lazy_images=True,
    )

    def preview(text, **kwargs):
        return obsidian.markdown_preview(
            text,
            int(app.preferences.values['markdown_font_size']),
            local_links=True,
            limits=preview_limits,
            compact_top=True,
            callouts=True,
            **kwargs,
        )

    def tab_style(button, selected):
        source_tab(button, selected)
        accessible_name(button, button.text + (' selected' if selected else ''))

    def folder_browser(*, open_folder, navigate):
        """Use supplied folder snapshots without storage indexing."""
        browser = FileBrowser(
            open_folder=open_folder, navigate=navigate, contextual_selection=False, preview=False,
        )
        browser.local_search = None
        browser.resource_search = None
        return browser

    def client():
        return getattr(app, 'cloud_client', None)

    def active():
        return app.active_host

    def privacy_gate():
        return getattr(app.cloud_client, 'session_privacy', None)

    def privacy_gates():
        return app.screen_privacy.gates()

    def storage(provider):
        return NotesDocumentAccess(
            provider, client=client, active=active, privacy_gate=privacy_gate,
            privacy_gates=privacy_gates,
        )

    def file_actions(owner, row):
        from ..file_items import row_actions
        provider = owner.provider
        root = owner.root if provider.private else str((provider.root / owner.root).resolve())
        return row_actions(app, provider, row, anchor=owner.reader_actions_button, opener=dict(kind='notes', root=root))

    return NotesHost(
        playlists=partial(_playlists, app),
        playlist_speech=partial(_playlist_speech, app),
        audio_output=lambda: for_app(app),
        folder_browser=folder_browser,
        show_error=partial(_show_error, app),
        remember_document=lambda owner: obsidian.remember_note(app, owner),
        open_resource=partial(_open_resource, app),
        relocate_references=lambda provider, source, destination: relocate(
            app, provider, source, destination,
        ),
        tab_style=tab_style,
        open_timing=_open_timing(timing_marker),
        document_editor=lambda library, path: notes_editor(app, library, path),
        confirm=partial(_confirm_save, app),
        choose_type=partial(_choose_type, app),
        drawer_host=notes_drawer_host(app),
        storage=storage,
        presentation=app.presentation,
        batch_rows=batch_surfaces,
        tree_rows=tree_rows,
        loop=app.loop,
        workspace=app.workspace,
        apple=app.routes.apple,
        client=client,
        active=active,
        privacy_gate=privacy_gate,
        privacy_gates=privacy_gates,
        content_width=lambda destination: app.adaptive.content_width(destination, margin=0),
        folder_visible=lambda *args, **kwargs: app.folder_path_visible(*args, **kwargs),
        show_documents=app.show_documents_hub,
        close_session=app.request_close_session,
        show_view=app.show_view,
        destination=lambda: app.native_host.state.destination,
        render=app.adaptive.render,
        speech=lambda *args, **kwargs: MarkdownSpeech(app, *args, **kwargs),
        commands=lambda button, *args: FeatureCommands(button, app, *args),
        file_actions=file_actions,
        list_button=list_button,
        middle_filename=middle_filename,
        entry_icon=entry_icon,
        breadcrumb_separator=breadcrumb_separator,
        highlight_entry=highlight_entry,
        preview=preview,
    )


async def _show_error(app, /, title, message):
    import toga

    await app.main_window.dialog(toga.ErrorDialog(title, message))


async def _confirm_save(app):
    from services.documents.authoring.document_dialogs import DocumentDialog

    return await app.main_window.dialog(DocumentDialog(
        'Save document changes?', 'Save this document before leaving it.',
        discard_label='Discard changes',
    ))


async def _choose_type(app):
    from services.documents.authoring.document_dialogs import DocumentTypeDialog

    choices = [('Ⓜ  Markdown', 'md')]
    if app.feature_enabled('notebooks'):
        choices.append(('▧  Remarkable Document', 'rmdoc'))
    return await app.main_window.dialog(DocumentTypeDialog(choices=choices))


def _open_timing(marker):
    if not marker.is_file():
        return None

    def record(sample):
        if not marker.is_file():
            return
        # Device diagnostics record numeric stages without document or provider data.
        from commonUtils.persistence import atomic_write_json

        try:
            atomic_write_json(marker.with_name('notes-open-timing.json'), sample, max_bytes=4096)
        except OSError:
            pass  # Optional measurement must not interrupt document opening.

    return record


async def _open_resource(app, /, provider, path, **options):
    from features.video.formats import VIDEO_EXTENSIONS

    if Path(path).suffix.lower() in VIDEO_EXTENSIONS:
        from services.documents.mobile_storage import open_provider_document

        return await open_provider_document(app, provider, path, **options)

    from ..document_sources import reopen_file
    from ..favourites import resource_reference

    source, _ = resource_reference(app, provider, path)
    return await reopen_file(app, source)


def _tree_row_factory(app):
    from features.notes_library.mobile.library_panels import ENTRY_ICON_SIZE, FILENAME_SIZE, PATH_SIZE

    def tree_rows(owner):
        if not type(app._impl).__module__.startswith(('toga_android.', 'toga_iOS.')):
            return None

        from features.notes_library.mobile.tree_rows import NativeTreeRows
        from ..hub_icons import icon
        from ..recycled_file_list import RecycledFileList

        def row_list(**kwargs):
            result = RecycledFileList(
                icon_size=ENTRY_ICON_SIZE,
                title_lines=2,
                row_height=56,
                body_text=FILENAME_SIZE,
                caption_text=PATH_SIZE,
                selection_role='notes_selection',
                **kwargs,
            )
            result.tree_landing_icon = icon('folder_document')
            return result

        return NativeTreeRows(owner, row_list)

    return tree_rows


def _playlists(app, /, library):
    from features.notes_library.playlists import PlaylistStore

    return PlaylistStore(app.private_root, app=app).for_library(library)


def _playlist_speech(app, /, owner, catalog, changed):
    from features.books.mobile.speech_view import ReadAloudPanel
    from features.notes_library.mobile.playlist_speech import PlaylistSpeech, playlist_panel_type
    from ..markdown_speech import clear_view, highlight_view, prepare_view, stop_markdown_speech

    return PlaylistSpeech(
        owner,
        catalog,
        changed,
        app=app,
        panel_type=playlist_panel_type(ReadAloudPanel),
        stop_markdown_speech=lambda: stop_markdown_speech(app),
        prepare_view=prepare_view,
        highlight_view=highlight_view,
        clear_view=clear_view,
    )
