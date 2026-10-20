"""Owned workflow state and explicit application services."""
from services.workflow_host import HostAttribute
from logisticsmobile.hub_ui import HubUI


class HubController(HubUI):
    METHODS = ('session_visible', 'recent_items', 'recent_opener', 'recent_row', 'build_home', 'reflow_home', 'reflow_documents_hub', 'build_documents_hub', 'search_documents', 'refresh_document_list', 'open_document_category', 'session_card', 'session_summary', 'session_panel', 'new_hub_document', 'open_hub_file', 'refresh_hub')
    FIELDS = ('document_categories', 'document_grids', 'document_launchers', 'document_search', 'document_open_list', 'document_recent_list', 'document_saved_list', 'home_actions', 'home_content', 'home_continue', 'home_continue_button', 'home_sections', 'documents_sections')

    def __init__(self, app):
        self.app = app

    adaptive = HostAttribute('adaptive')
    checkpoint = HostAttribute('checkpoint')
    choose_document_type = HostAttribute('choose_document_type')
    cloud_restore_task = HostAttribute('cloud_restore_task')
    folder_picker_or_error = HostAttribute('folder_picker_or_error')
    main_window = HostAttribute('main_window')
    open_book = HostAttribute('open_book')
    open_document = HostAttribute('open_document')
    preferences = HostAttribute('preferences')
    private_sessions = HostAttribute('private_sessions')
    reader_manager = HostAttribute('reader_manager')
    recent_documents = HostAttribute('recent_documents')
    refresh_documents = HostAttribute('refresh_documents')
    register_transfer_status = HostAttribute('register_transfer_status')
    routes = HostAttribute('routes')
    session_closer = HostAttribute('session_closer')
    session_opener = HostAttribute('session_opener')
    show_cloud = HostAttribute('show_cloud')
    start_cloud_restore = HostAttribute('start_cloud_restore')
    show_documents = HostAttribute('show_documents')
    show_home_files = HostAttribute('show_home_files')
    show_library = HostAttribute('show_library')
    store = HostAttribute('store')
    text_views = HostAttribute('text_views')
    window_id = HostAttribute('window_id')
    workspace = HostAttribute('workspace')
