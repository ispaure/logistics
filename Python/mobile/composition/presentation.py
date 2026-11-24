"""Application composition of feature-facing presentation services."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from .notes import notes_drawer_host as notes_drawer_host, notes_host as notes_host


def rclone_host_ui(app):
    from features.rclone.mobile.host import MobileHostUI, ConnectionPresentation
    from mobile.control_icons import icon_button
    from mobile.browser_ui import FileBrowser as NativeBrowser, refresh_download_directory
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
    from mobile import transfer_notifications
    async def offer_notes(browser, provider, root, rows):
        return False  # Notes Libraries are launched explicitly from Documents.
    from mobile.settings.forms import (
        ConnectionSettingsPage,
        connection_group,
        connection_field,
        connection_note,
        connection_heading,
        connection_disclosure,
        credential_package_row,
        CredentialStorageContent,
    )

    return MobileHostUI(
        offer_notes=offer_notes,
        refresh_transfer_chrome=lambda: refresh_transfer_chrome(app),
        transfer_foreground=lambda: (transfer_notifications.foreground(app)
                                     and not transfer_notifications.covered(app)),
        publish_transfer_notice=lambda notice, action: transfer_notifications.for_app(app).publish(notice, action),
        icon_button=icon_button,
        NativeBrowser=NativeBrowser,
        FeatureCommands=lambda button, owner, *args, **kwargs: FeatureCommands(
            button, app, *args, **kwargs
        ),
        private_label=private_label,
        visible_remotes=visible_remotes,
        exclusions=exclusions,
        pick_document=lambda: pickers.pick_document(app),
        ResourceImports=ResourceImports,
        export_file=lambda owner, selected: pickers.export_file(app, selected),
        accessible_name=accessible_name,
        local_read_available=lambda owner, **kwargs: local_read_available(
            app, **kwargs
        ),
        refresh_folder_source_actions=lambda: source_actions(app),
        refresh_download_directory=lambda provider, target: refresh_download_directory(app, provider, target),
        settings=ConnectionPresentation(
            page=lambda *args: ConnectionSettingsPage(app, *args),
            group=connection_group,
            field=connection_field,
            note=connection_note,
            heading=connection_heading,
            disclosure=connection_disclosure,
            package_row=credential_package_row,
            storage_content=CredentialStorageContent,
        ),
        record_folder=lambda *args, **kwargs: record(app, *args, **kwargs),
        opening_status=lambda source, **kwargs: opening_status(app, source, **kwargs),
    )


def mobile_presentation(app):
    from services.mobile_presentation import MobilePresentation
    from mobile.control_icons import icon_button
    from mobile.control_icons import apply_icon
    from mobile.appearance import action_button
    from mobile.action_menu import ActionMenu, NativeMenu
    from mobile.appearance import surface
    from mobile.appearance import accessible_name, apple_color
    from mobile.workspace_navigation import menu_button
    from mobile.pickers import export_document
    from mobile.preview import markdown_preview
    from mobile.palette import css_variables
    from mobile.recycled_file_list import summary_list
    from mobile.font_scaling import bind, font_size
    from mobile.document_sources import folder_action
    from mobile.fold_layout import reserved_divisions, division, is_iphone_duo
    from mobile.document_location import bind_apple_hold
    from mobile.reading.reader_edges import clear_notebook_rail, compact_apple_reader
    from mobile.reader_top_band import NOTEBOOK_TOOLBAR_CLEARANCE, reset_notebook_clearance
    from mobile.layout_participants import participants
    from mobile.favourites import favourite_resource
    from mobile.filename_input import FilenameInput
    from mobile.scroll_edges import fill_bottom

    def refresh_notebook_layout(view):
        container = view._impl.container
        if container is not None and compact_apple_reader(container, notebook=view):
            container.content.interface.refresh()

    return MobilePresentation(
        icon_button=icon_button,
        apply_icon=apply_icon,
        action_button=action_button,
        ActionMenu=ActionMenu,
        NativeMenu=NativeMenu,
        surface=surface,
        apple_color=apple_color,
        menu_button=menu_button,
        export_document=lambda owner, *args, **kwargs: export_document(
            app, *args, **kwargs
        ),
        markdown_preview=markdown_preview,
        css_variables=css_variables,
        summary_list=summary_list,
        font_size=lambda kind: font_size(app, kind),
        bind_font=lambda widget, kind, **kwargs: bind(app, widget, kind, **kwargs),
        folder_actions=lambda session: folder_action(app, session),
        reserved_divisions=reserved_divisions,
        fold_division=lambda widget: division(app, widget),
        is_iphone_duo=is_iphone_duo,
        reset_reader_layout=reset_notebook_clearance,
        accessible_name=accessible_name,
        bind_apple_hold=bind_apple_hold,
        notebook_toolbar_clearance=NOTEBOOK_TOOLBAR_CLEARANCE,
        native_notebook_toolbar=False,
        refresh_notebook_layout=refresh_notebook_layout,
        clear_notebook_rail=clear_notebook_rail,
        register_layout=lambda *args, **kwargs: participants(app).register(*args, **kwargs),
        filename_input=FilenameInput,
        fill_scroll_bottom=fill_bottom,
        favourite_resource=lambda provider, path, **kwargs: favourite_resource(app, provider, path, **kwargs),
    )


def library_host(app):
    from features.books.mobile.library.catalog import LibraryHost
    from .. import library_ui
    from ..files_ui import local_read_available

    async def open_folder(library, *, destination='files'):
        provider = library["provider"]

        def current():
            return not provider.private or (
                app.cloud_client is library["client"]
                and app.cloud_client.generation == library["generation"]
            )

        if not current():
            return False
        app.cloud_controller().show_cloud(present=False)
        if not current() or not local_read_available(app, private=provider.private):
            return
        if destination == 'documents':
            return await app.hub_controller().browse_document_library(
                library['source'], folder=library['folder'], title=library['name'], provider=provider, category='Comics')
        await app.show_files(local_root=not provider.private)
        if not current():
            return False
        label = library["source"] if provider.private else "Local files"
        app.file_roots[label] = provider
        app.update_file_locations()
        await app.browser_file_location((label, library["folder"]))

    return LibraryHost(
        presentation=app.presentation,
        folder_visible=lambda record: app.library_folder_visible(record),
        show_locations=app.show_locations,
        open_folder=open_folder,
        snapshot=lambda: (
            getattr(app, "cloud_client", None),
            [dict(job) for job in app.mirror_store().jobs.values()],
            tuple(getattr(app, "cloud_crypt_remotes", ())),
        ),
        discover=lambda *args: library_ui.discover_libraries(*args),
    )


def speech_presentation(app):
    from features.books.mobile.speech_host import SpeechPresentation
    from features.books.mobile.media_controls import SpeechPlayback
    from ..audio_output import for_app
    from ..control_icons import icon_button, apply_icon
    from ..appearance import surface, accessible_name
    from ..speech_overlay import SpeechOverlay

    return SpeechPresentation(
        icon_button=icon_button,
        apply_icon=apply_icon,
        surface=surface,
        accessible_name=accessible_name,
        overlay=lambda panel, owner, **kwargs: SpeechOverlay(
            panel, owner, app, **kwargs
        ),
        voice=lambda: app.preferences.values.get("speech_voice", ""),
        playback=lambda panel, **kwargs: SpeechPlayback(panel, app, audio_output=for_app(app), **kwargs),
    )


def reading_presentation(owner):
    from services.documents.mobile_reading import ReadingPresentation
    from ..fold_layout import reading_seam, seam_gap, page_region, comic_mode
    from ..layout_events import layout_waiter, notify_layout
    from ..reader_controls import provider_comic_path
    from ..palette import themed_chapter
    from ..provider_ui import private_label, speech_session_valid

    app = getattr(owner, "app", owner)
    from ..comic_feedback import boundary, clear
    from ..external_display import sharing

    return ReadingPresentation(
        seam=lambda view: reading_seam(owner, view),
        seam_gap=lambda view: seam_gap(owner, view),
        page_region=lambda view: page_region(owner, view),
        mode=lambda view: comic_mode(owner, view),
        layout_changed=lambda: layout_waiter(app),
        content_width=lambda destination: app.adaptive.content_width(
            destination, margin=0
        ),
        private_label=private_label,
        speech_valid=lambda: speech_session_valid(owner),
        speech_presentation=app.speech_presentation,
        highlight_allowed=lambda: not app.screen_privacy.inactive,
        comic_path=provider_comic_path,
        notify_layout=lambda: notify_layout(app),
        themed_chapter=themed_chapter,
        comic_boundary=lambda direction, **kwargs: boundary(owner, direction, **kwargs),
        clear_comic_boundary=lambda: clear(app, owner=owner),
        comic_sharing=lambda: sharing(app),
    )


def provider_markdown(owner, view, footer):
    """Compose the Markdown workflow without exposing the host to the feature."""
    from services.documents.authoring.provider_markdown import (
        ProviderMarkdown,
        ProviderMarkdownHost,
    )
    from .. import preview
    from ..control_icons import icon_button, apply_icon
    from ..font_scaling import bind
    from ..palette import css_variables
    from ..markdown_speech import MarkdownSpeech
    from ..action_menu import FeatureCommands
    from ..provider_ui import private_label, speech_session_valid
    from ..workspace_navigation import sync_reader_toolbar

    from services.documents.mobile_reading import reading_capabilities

    app = owner.app

    def valid(reader):
        if (
            reader is None
            or owner.crypt_reader is not reader
            or getattr(owner, "_provider_markdown", None) is not workflow
            or owner.session.id not in app.workspace.sessions
            or not speech_session_valid(owner)
        ):
            return False
        return True

    def access_stamp():
        return id(getattr(owner, 'document_access', None))

    def sync_toolbar():
        if (
            getattr(owner, "_provider_markdown", None) is workflow
            and owner.crypt_view in app.routes.body().children
        ):
            sync_reader_toolbar(app, owner.crypt_view)

    title, actions_button = view.crypt_title, view.crypt_actions
    host = ProviderMarkdownHost(
        presentation=app.presentation,
        loop=owner.loop,
        reader=lambda: owner.crypt_reader,
        valid=valid,
        access_stamp=access_stamp,
        render=lambda *args, **kwargs: preview.markdown_preview(*args, **kwargs),
        image_source=lambda reader: preview.reader_image_source(
            owner._crypt_reader_store, reader
        ),
        font_size=lambda: int(owner.preferences.values["markdown_font_size"]),
        stylesheet=css_variables,
        bind_font=lambda widget, **kwargs: bind(owner, widget, "markdown", **kwargs),
        busy=lambda: owner.cloud_busy,
        transfer_busy=lambda: owner.transfer_busy,
        speech=lambda web, content, current: MarkdownSpeech(
            app,
            web,
            content,
            privacy_gate=lambda: getattr(owner, "privacy_gate", None),
            valid=current,
        ),
        commands=lambda actions: FeatureCommands(
            actions_button, owner, actions, owner.show_private_tools, document=True
        ),
        sync_toolbar=sync_toolbar,
        error=lambda message: setattr(title, "text", private_label(message)),
        icon_button=icon_button,
        apply_icon=apply_icon,
    )
    workflow = ProviderMarkdown(
        host,
        source=view.crypt_text,
        content=view.crypt_content,
        toolbar=view.reader_toolbar,
        save=view.crypt_save,
        actions=view.crypt_actions,
        footer=footer,
        action_items=view.crypt_action_items,
        actions_menu=view.crypt_actions_menu,
        read_only=getattr(view.crypt_reader, "read_only", False),
        private=reading_capabilities(view._crypt_reader_store).private,
    )
    return workflow


def file_operations(owner, *, drawer=None):
    """Bind captured controls and existing global busy policy to the file worker."""
    from dataclasses import dataclass
    from ..file_operations import FileOperations, FileOperationsHost
    browser_owner = owner if drawer is None else drawer

    @dataclass(frozen=True)
    class OperationView:
        controls: tuple
        status: object
        action_status: object
        stamp: tuple

    def stamp():
        client = getattr(owner, "cloud_client", None)
        return (
            id(owner.file_operation_view if drawer is None else drawer.page),
            id(browser_owner.file_browser),
            id(browser_owner.file_provider),
            browser_owner.file_path,
            owner.navigation_generation,
            id(client),
            getattr(client, "generation", None),
        )

    def allowed(mutation):
        return (
            owner.active_host
            and not owner.cloud_busy
            and (not mutation or owner.clear_private_reader())
        )

    async def prepare(request, mutation):
        from ..file_operations import FileOperationRequest
        if isinstance(request, FileOperationRequest) and request.kind in {'rename', 'move'}:
            from ..document_mutations import prepare_document_mutation
            return await prepare_document_mutation(owner, request)
        if isinstance(request, FileOperationRequest) and request.kind in {'new', 'copy'}:
            return None
        if mutation and not owner.clear_private_reader():
            raise ValueError('Save or close open file edits before changing files.')

    def begin(cancel):
        if drawer is None:
            row = owner.file_rows.get(owner.file_selection.value)
            owner._file_selected = owner.file_provider, row["path"] if row else None
            controls = (
                owner.file_storage,
                owner.file_location,
                owner.file_selection,
                owner.file_name,
                owner.file_destination,
                owner.file_target,
                owner.file_password,
                owner.file_actions_button,
            )
        else:
            controls = (drawer.folder_select_button,)
        view = OperationView(
            controls, browser_owner.file_status,
            owner.file_action_status if drawer is None else None, stamp()
        )
        for control in controls:
            control.enabled = False
        owner.set_cloud_busy(True)
        owner._crypt_cancel = cancel
        return view

    def current(view):
        return (
            owner.active_host
            and view.stamp == stamp()
            and browser_owner.file_status is view.status
            and getattr(owner, "_crypt_cancel", None) is operations.cancel_event
        )

    def report(view, message):
        view.status.value = message

    def finish(view, cancel):
        if getattr(owner, "_crypt_cancel", None) is not cancel:
            return
        visible = current(view)
        owner._crypt_cancel = None
        if not owner.active_host:
            owner.cloud_busy = False
            return
        if visible and view.action_status is not None:
            view.action_status.text = view.status.value
        try:
            owner.set_cloud_busy(False)
            if visible and drawer is None and view.stamp == stamp():
                owner.refresh_downloads()
        finally:
            for control in view.controls:
                control.enabled = True

    operations = FileOperations(
        FileOperationsHost(
            allowed=allowed, begin=begin, current=current, report=report, finish=finish, prepare=prepare
        )
    )
    return operations
