"""Owned workflow state and explicit application services."""

from dataclasses import dataclass
from typing import Any
from services.workflow_host import HostAttribute, HostService, StateAttribute
from .smb_connection import SMBConnection, SMBFormState
from .downloads import DownloadWorkflow, DownloadState
from .credentials_ui import CredentialWorkflow, CredentialState
from features.rclone.mobile.cloud_ui import CloudUI, CloudBrowserPresentation
from .browser_workflow import RemoteBrowserState, RemoteBrowserWorkflow


@dataclass
class CloudState:
    busy: bool = False
    client: Any = None


class CloudController(CloudUI):
    METHODS = (
        "remote_activity",
        "show_cloud",
        "browse_cloud_path",
        "show_cloud_actions",
        "show_remote_item_actions",
        "show_cloud_connections",
        "begin_cloud_import",
        "show_cloud_import",
        "refresh_retained_credentials",
        "loaded_remote_names",
        "set_loaded_remote_names",
        "lock_cloud",
        "show_smb_connection",
        "change_smb_guest",
        "connect_smb",
        "selected_cloud_remote",
        "set_cloud_busy",
        "cloud_remote_changed",
        "refresh_cloud_remote_help",
        "_load_crypt_remote_names",
        "retained_packages",
        "remember_credential_association",
        "visible_remote_names",
        "package_remote_names",
        "remember_loaded_packages",
        "loaded_package_label",
        "credential_groups",
        "retained_credential_associations",
        "home_unlock_candidates",
        "show_home_unlock",
        "require_remote_credentials_async",
        "require_remote_credentials",
        "show_retained_unlock",
        "restore_cloud",
        "probe_cloud",
        "choose_cloud_package",
        "import_cloud_package",
        "browse_cloud",
        "parent_cloud",
        "browser_cloud_selected",
        "browser_cloud_folder",
        "browser_cloud_location",
        "open_cloud_folder",
        "open_remote_document",
        "cancel_cloud",
        "clear_cloud",
        "refresh_downloads",
        "open_download",
        "export_download",
        "build_localcrypt",
        "refresh_crypt",
        "use_downloaded_file",
    )
    FIELDS = (
        "_remote_activities",
        "cloud_import_entry",
        "cloud_import_view",
        "cloud_connections_status",
        "cloud_settings_toggle",
        "cloud_advanced_view",
        "cloud_browse",
        "cloud_busy",
        "cloud_cancel",
        "cloud_choose",
        "cloud_clear",
        "cloud_client",
        "cloud_connections_view",
        "cloud_crypt_remotes",
        "cloud_entries",
        "cloud_import",
        "cloud_import_message",
        "cloud_location",
        "cloud_lock",
        "cloud_open",
        "cloud_open_remote",
        "cloud_package",
        "cloud_password",
        "cloud_path",
        "cloud_pending_zip",
        "cloud_probe",
        "cloud_reload",
        "cloud_remember",
        "cloud_remote",
        "cloud_remote_generation",
        "cloud_remote_heading",
        "cloud_remote_help",
        "cloud_restore_task",
        "cloud_retained_box",
        "cloud_retained_buttons",
        "cloud_rows",
        "cloud_selected_zip",
        "cloud_status",
        "cloud_transfer_progress",
        "cloud_up",
        "cloud_view",
        "credential_packages",
        "credential_unlock_button",
        "credential_unlock_password",
        "credential_unlock_status",
        "crypt_copies",
        "crypt_labels",
        "crypt_open",
        "crypt_password",
        "crypt_refresh",
        "crypt_resume",
        "crypt_selector",
        "download_export",
        "download_labels",
        "download_open",
        "download_selector",
        "downloads",
        "file_path",
        "file_rows",
        "remote_browser",
        "remote_item_password",
        "remote_item_view",
        "remote_read_busy",
        "resource_imports",
        "session_credential_packages",
        "smb_guest",
        "smb_account",
        "smb_signin",
        "smb_advanced_toggle",
        "smb_help_toggle",
        "smb_connect",
        "smb_domain",
        "smb_host",
        "smb_name",
        "smb_password",
        "smb_port",
        "smb_remember",
        "smb_status",
        "smb_user",
        "smb_view",
    )

    METHODS += ("prepare_cloud", "start_cloud_restore")

    def __init__(self, app):
        self.app = app
        self.credential_state = CredentialState()
        self.credential_workflow = CredentialWorkflow(self)
        self.download_state = DownloadState()
        self.download_workflow = DownloadWorkflow(self)
        self.state = CloudState()
        self.browser_state = RemoteBrowserState()
        self.browser_workflow = RemoteBrowserWorkflow(
            self.browser_state, CloudBrowserPresentation(self)
        )
        self.smb_form = SMBFormState()
        self.smb_connection = SMBConnection(self, self.smb_form)

    downloads = StateAttribute("download_state", "downloads")
    download_labels = StateAttribute("download_state", "download_labels")
    download_selector = StateAttribute("download_state", "download_selector")
    download_export = StateAttribute("download_state", "download_export")
    download_open = StateAttribute("download_state", "download_open")
    resource_imports = StateAttribute("download_state", "resource_imports")

    credential_packages = StateAttribute("credential_state", "credential_packages")
    session_credential_packages = StateAttribute(
        "credential_state", "session_credential_packages"
    )
    cloud_pending_zip = StateAttribute("credential_state", "cloud_pending_zip")

    cloud_busy = StateAttribute("state", "busy")
    cloud_client = StateAttribute("state", "client")
    remote_read_busy = StateAttribute("browser_state", "reading")
    cloud_path = StateAttribute("browser_state", "path")
    cloud_open_remote = StateAttribute("browser_state", "remote")
    cloud_rows = StateAttribute("browser_state", "rows")
    smb_account = StateAttribute("smb_form", "smb_account")
    smb_advanced_toggle = StateAttribute("smb_form", "smb_advanced_toggle")
    smb_connect = StateAttribute("smb_form", "smb_connect")
    smb_domain = StateAttribute("smb_form", "smb_domain")
    smb_guest = StateAttribute("smb_form", "smb_guest")
    smb_help_toggle = StateAttribute("smb_form", "smb_help_toggle")
    smb_host = StateAttribute("smb_form", "smb_host")
    smb_name = StateAttribute("smb_form", "smb_name")
    smb_password = StateAttribute("smb_form", "smb_password")
    smb_port = StateAttribute("smb_form", "smb_port")
    smb_remember = StateAttribute("smb_form", "smb_remember")
    smb_signin = StateAttribute("smb_form", "smb_signin")
    smb_status = StateAttribute("smb_form", "smb_status")
    smb_user = StateAttribute("smb_form", "smb_user")
    smb_view = StateAttribute("smb_form", "smb_view")

    _crypt_cancel = HostAttribute("_crypt_cancel")
    _folder_opening = HostAttribute("_folder_opening")
    _storage_changing = HostAttribute("_storage_changing")
    active_host = HostAttribute("active_host")
    build_file_manager = HostAttribute("build_file_manager")
    clear_private_catalog = HostAttribute("clear_private_catalog")
    clear_private_reader = HostService("clear_private_reader")
    file_provider = HostAttribute("file_provider")
    file_status = HostAttribute("file_status")
    file_work = HostAttribute("file_work")
    folder_choices = HostService("folder_choices")
    folder_hub_error = HostAttribute("folder_hub_error")
    folder_loading_status = HostAttribute("folder_loading_status")
    folder_path_visible = HostService("folder_path_visible")
    folder_picker_status = HostAttribute("folder_picker_status")
    legacy_name_visible = HostService("legacy_name_visible")
    loop = HostAttribute("loop")
    main_window = HostAttribute("main_window")
    native_host = HostAttribute("native_host")
    navigation_generation = HostAttribute("navigation_generation")
    open_book = HostAttribute("open_book")
    open_crypt = HostService("open_crypt")
    open_document = HostAttribute("open_document")
    pin_remote_folder = HostService("pin_remote_folder")
    populate_file_browser = HostAttribute("populate_file_browser")
    preferences = HostAttribute("preferences")
    private_root = HostAttribute("private_root")
    private_sessions = HostAttribute("private_sessions")
    rclone_ui = HostService("rclone_ui")
    reader_manager = HostAttribute("reader_manager")
    readers = HostAttribute("readers")
    refresh_documents = HostAttribute("refresh_documents")
    refresh_folder_actions = HostService("refresh_folder_actions")
    refresh_hub_crypt_locations = HostService("refresh_hub_crypt_locations")
    refresh_library = HostAttribute("refresh_library")
    resume_crypt = HostService("resume_crypt")
    routes = HostAttribute("routes")
    screen_privacy = HostAttribute("screen_privacy")
    set_file_items = HostAttribute("set_file_items")
    show_documents = HostService("show_documents")
    show_locations = HostService("show_locations")
    show_view = HostService("show_view")
    store = HostAttribute("store")
    transfer_busy = HostAttribute("transfer_busy")
