"""Application composition of feature-facing presentation services."""


def rclone_host_ui(app):
    from features.rclone.mobile.host import MobileHostUI, ConnectionPresentation
    from mobile.control_icons import icon_button
    from mobile.browser_ui import FileBrowser as NativeBrowser
    from mobile.action_menu import FeatureCommands
    from mobile.provider_ui import private_label
    from mobile.folder_hub import visible_remotes
    from mobile.folder_hub import exclusions
    from mobile import pickers
    from mobile.resource_imports import ResourceImports
    from mobile.appearance import accessible_name
    from mobile.folder_hub_style import source_actions
    from mobile.files_ui import local_read_available
    from mobile.folder_navigation import record
    from mobile.document_sources import opening_status
    from mobile.reader_chrome import refresh_transfer_chrome
    from mobile.settings_ui import ConnectionSettingsPage, connection_group, connection_field, connection_note, connection_heading, connection_disclosure
    return MobileHostUI(refresh_transfer_chrome=lambda: refresh_transfer_chrome(app), icon_button=icon_button, NativeBrowser=NativeBrowser, FeatureCommands=lambda button, owner, *args, **kwargs: FeatureCommands(button, app, *args, **kwargs), private_label=private_label, visible_remotes=visible_remotes, exclusions=exclusions, pick_document=lambda owner: pickers.pick_document(app), ResourceImports=ResourceImports, export_file=lambda owner, selected: pickers.export_file(app, selected), accessible_name=accessible_name, local_read_available=lambda owner, **kwargs: local_read_available(app, **kwargs), refresh_folder_source_actions=lambda: source_actions(app), settings=ConnectionPresentation(page=lambda *args: ConnectionSettingsPage(app, *args),
            group=connection_group, field=connection_field, note=connection_note,
            heading=connection_heading, disclosure=connection_disclosure), record_folder=lambda *args, **kwargs: record(app, *args, **kwargs), opening_status=lambda source, **kwargs: opening_status(app, source, **kwargs))


def mobile_presentation(app):
    from services.mobile_presentation import MobilePresentation
    from mobile.control_icons import icon_button
    from mobile.control_icons import apply_icon
    from mobile.appearance import action_button
    from mobile.action_menu import ActionMenu, NativeMenu
    from mobile.appearance import surface
    from mobile.appearance import apple_color
    from mobile.workspace_navigation import menu_button
    from mobile.pickers import export_document
    from mobile.preview import markdown_preview
    from mobile.palette import css_variables
    from mobile.recycled_file_list import summary_list
    from mobile.font_scaling import bind, font_size
    from mobile.document_sources import folder_action
    return MobilePresentation(icon_button=icon_button, apply_icon=apply_icon, action_button=action_button, ActionMenu=ActionMenu, NativeMenu=NativeMenu, surface=surface, apple_color=apple_color, menu_button=menu_button, export_document=lambda owner, *args, **kwargs: export_document(app, *args, **kwargs), markdown_preview=markdown_preview, css_variables=css_variables, summary_list=summary_list, font_size=lambda kind: font_size(app, kind), bind_font=lambda widget, kind, **kwargs: bind(app, widget, kind, **kwargs), folder_actions=lambda session: folder_action(app, session))


def library_host(app):
    from features.books.mobile.library.catalog import LibraryHost
    from .. import library_ui
    from ..files_ui import local_read_available
    async def open_folder(library):
        provider = library['provider']
        def current():
            return not provider.private or (app.cloud_client is library['client']
                and app.cloud_client.generation == library['generation'])
        if not current():
            return False
        app.show_cloud(present=False)
        if not local_read_available(app, private=provider.private):
            return
        await app.show_files(local_root=not provider.private)
        if not current():
            return False
        label = library['source'] if provider.private else 'Local files'
        app.file_roots[label] = provider
        app.update_file_locations()
        await app.browser_file_location((label, library['folder']))
    return LibraryHost(presentation=app.presentation, folder_visible=lambda record: app.library_folder_visible(record),
        show_locations=app.show_locations, open_folder=open_folder,
        snapshot=lambda: (getattr(app, 'cloud_client', None),
            [dict(job) for job in app.mirror_store().jobs.values()], tuple(getattr(app, 'cloud_crypt_remotes', ()))),
        discover=lambda *args: library_ui.discover_libraries(*args))


def speech_presentation(app):
    from features.books.mobile.speech_host import SpeechPresentation
    from features.books.mobile.media_controls import SpeechPlayback
    from ..control_icons import icon_button, apply_icon
    from ..appearance import surface, accessible_name
    from ..speech_overlay import SpeechOverlay
    return SpeechPresentation(icon_button=icon_button, apply_icon=apply_icon,
        surface=surface, accessible_name=accessible_name,
        overlay=lambda panel, owner, **kwargs: SpeechOverlay(panel, owner, app, **kwargs),
        voice=lambda: app.preferences.values.get('speech_voice', ''),
        playback=lambda panel, **kwargs: SpeechPlayback(panel, app, **kwargs))


def notes_host(app):
    from features.text_editor.mobile.notes_library import NotesHost
    from ..appearance import list_button
    from ..browser_ui import middle_filename, entry_icon, highlight_entry
    from ..markdown_speech import MarkdownSpeech
    from ..action_menu import FeatureCommands
    from .. import obsidian
    async def open_editor(provider, path, destination, remote, client):
        from features.text_editor.resources import LocalTextCopies
        from features.rclone.localcrypt.mobile.resources import encrypted_document
        if remote:
            from features.rclone.mobile.remote_readers import RemoteReaders
            return await app.open_crypt(copies=RemoteReaders(client, provider.remote), key=path)
        source = encrypted_document(provider, path)
        copies, key = source if source is not None else (LocalTextCopies(provider), path)
        return await app.open_crypt(copies=copies, key=key, destination=destination)
    return NotesHost(presentation=app.presentation, loop=app.loop, workspace=app.workspace,
        apple=app.routes.apple, client=lambda: getattr(app, 'cloud_client', None), active=lambda: app.active_host,
        privacy_gate=lambda: getattr(app.cloud_client, 'session_privacy', None),
        privacy_gates=lambda: app.screen_privacy.gates(),
        content_width=lambda destination: app.adaptive.content_width(destination, margin=0),
        folder_visible=lambda *args, **kwargs: app.folder_path_visible(*args, **kwargs),
        show_documents=app.show_documents_hub, show_view=app.show_view,
        destination=lambda: app.native_host.state.destination, render=app.adaptive.render,
        open_editor=open_editor, speech=lambda *args, **kwargs: MarkdownSpeech(app, *args, **kwargs),
        commands=lambda button, *args: FeatureCommands(button, app, *args),
        list_button=list_button, middle_filename=middle_filename, entry_icon=entry_icon,
        highlight_entry=highlight_entry,
        preview=lambda text: obsidian.markdown_preview(text, int(app.preferences.values['markdown_font_size']), local_links=True))


def reading_presentation(owner):
    from services.documents.mobile_reading import ReadingPresentation
    from ..fold_layout import reading_seam, seam_gap, page_region, comic_mode
    from ..layout_events import layout_waiter, notify_layout
    from ..reader_controls import provider_comic_path
    from ..palette import themed_chapter
    from ..provider_ui import private_label, speech_session_valid
    app = getattr(owner, 'app', owner)
    from ..comic_feedback import boundary, clear
    from ..external_display import sharing
    return ReadingPresentation(seam=lambda view: reading_seam(owner, view),
        seam_gap=lambda view: seam_gap(owner, view),
        page_region=lambda view: page_region(owner, view),
        mode=lambda view: comic_mode(owner, view), layout_changed=lambda: layout_waiter(app),
        content_width=lambda destination: app.adaptive.content_width(destination, margin=0),
        private_label=private_label, speech_valid=lambda: speech_session_valid(owner), speech_presentation=app.speech_presentation,
        highlight_allowed=lambda: not app.screen_privacy.inactive,
        comic_path=provider_comic_path, notify_layout=lambda: notify_layout(app), themed_chapter=themed_chapter,
        comic_boundary=lambda direction, **kwargs: boundary(owner, direction, **kwargs),
        clear_comic_boundary=lambda: clear(app, owner=owner),
        comic_sharing=lambda: sharing(app))


def provider_markdown(owner, view, footer):
    """Compose the Markdown workflow without exposing the host to the feature."""
    from features.text_editor.mobile.provider_markdown import ProviderMarkdown, ProviderMarkdownHost
    from .. import preview
    from ..control_icons import icon_button, apply_icon
    from ..font_scaling import bind
    from ..palette import css_variables
    from ..markdown_speech import MarkdownSpeech
    from ..action_menu import FeatureCommands
    from ..provider_ui import private_label, speech_session_valid
    from ..workspace_navigation import sync_reader_toolbar
    app = owner.app

    def valid(reader):
        if (reader is None or owner.crypt_reader is not reader
                or getattr(owner, '_provider_markdown', None) is not workflow
                or owner.session.id not in app.workspace.sessions
                or not speech_session_valid(owner)):
            return False
        store = owner._crypt_reader_store
        return (not (getattr(store, 'encrypted', True) or getattr(store, 'remote_storage', False))
                or owner.credential_client is app.cloud_client)

    def access_stamp():
        client = getattr(owner, 'credential_client', None)
        return id(client), getattr(client, 'generation', None), id(getattr(app, 'cloud_client', None))

    def sync_toolbar():
        if (getattr(owner, '_provider_markdown', None) is workflow
                and owner.crypt_view in app.routes.body().children):
            sync_reader_toolbar(app, owner.crypt_view)

    title, actions_button = view.crypt_title, view.crypt_actions
    host = ProviderMarkdownHost(loop=owner.loop, reader=lambda: owner.crypt_reader,
        valid=valid, access_stamp=access_stamp,
        render=lambda *args, **kwargs: preview.markdown_preview(*args, **kwargs),
        image_source=lambda reader: preview.reader_image_source(owner._crypt_reader_store, reader),
        font_size=lambda: int(owner.preferences.values['markdown_font_size']), stylesheet=css_variables,
        bind_font=lambda widget, **kwargs: bind(owner, widget, 'markdown', **kwargs),
        busy=lambda: owner.cloud_busy, transfer_busy=lambda: owner.transfer_busy,
        speech=lambda web, content, current: MarkdownSpeech(app, web, content,
            privacy_gate=lambda: getattr(owner, 'privacy_gate', None), valid=current),
        commands=lambda actions: FeatureCommands(actions_button, owner, actions, owner.show_private_tools, document=True),
        sync_toolbar=sync_toolbar, error=lambda message: setattr(title, 'text', private_label(message)),
        icon_button=icon_button, apply_icon=apply_icon)
    workflow = ProviderMarkdown(host, source=view.crypt_text, content=view.crypt_content,
        toolbar=view.reader_toolbar, save=view.crypt_save, actions=view.crypt_actions,
        footer=footer, action_items=view.crypt_action_items, actions_menu=view.crypt_actions_menu,
        read_only=getattr(view.crypt_reader, 'read_only', False))
    return workflow


def file_operations(owner):
    """Bind captured controls and existing global busy policy to the file worker."""
    from dataclasses import dataclass
    from ..file_operations import FileOperations, FileOperationsHost

    @dataclass(frozen=True)
    class OperationView:
        controls: tuple
        status: object
        action_status: object
        stamp: tuple

    def stamp():
        client = getattr(owner, 'cloud_client', None)
        return (id(owner.file_operation_view), id(owner.file_browser), id(owner.file_provider),
                owner.file_path, owner.navigation_generation, id(client), getattr(client, 'generation', None))

    def allowed(mutation):
        return (owner.active_host and not owner.cloud_busy
                and (not mutation or owner.clear_private_reader()))

    def begin(cancel):
        row = owner.file_rows.get(owner.file_selection.value)
        owner._file_selected = owner.file_provider, row['path'] if row else None
        controls = (owner.file_storage, owner.file_location, owner.file_selection, owner.file_name,
                    owner.file_destination, owner.file_target, owner.file_password, owner.file_actions_button)
        view = OperationView(controls, owner.file_status, owner.file_action_status, stamp())
        for control in controls:
            control.enabled = False
        owner.set_cloud_busy(True)
        owner._crypt_cancel = cancel
        return view

    def current(view):
        return (owner.active_host and view.stamp == stamp() and owner.file_status is view.status
                and getattr(owner, '_crypt_cancel', None) is operations.cancel_event)

    def report(view, message):
        view.status.value = message

    def finish(view, cancel):
        if getattr(owner, '_crypt_cancel', None) is not cancel:
            return
        visible = current(view)
        owner._crypt_cancel = None
        if not owner.active_host:
            owner.cloud_busy = False
            return
        if visible:
            view.action_status.text = view.status.value
        try:
            owner.set_cloud_busy(False)
            if visible and view.stamp == stamp():
                owner.refresh_downloads()
        finally:
            for control in view.controls:
                control.enabled = True

    operations = FileOperations(FileOperationsHost(allowed=allowed, begin=begin, current=current,
                                                   report=report, finish=finish))
    return operations
