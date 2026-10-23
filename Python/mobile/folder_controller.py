"""Owned workflow state and explicit application services."""

from copy import deepcopy
from services.workflow_host import HostAttribute, HostService
from .folder_discovery import FolderDiscovery, FolderDiscoveryHost
from .folder_hub import FolderDiscoverySnapshot
from mobile.folder_hub_ui import FolderHubUI


class FolderController(FolderHubUI):
    METHODS = (
        "legacy_name_visible",
        "folder_path_visible",
        "library_folder_visible",
        "change_show_legacy",
        "refresh_folder_visibility",
        "refresh_folder_hub",
        "refresh_hub_crypt_locations",
        "folder_choices",
        "show_folder_picker",
        "folder_picker_or_error",
        "selected_folder_credential",
        "set_folder_loading",
        "build_folder_picker",
        "update_folder_list",
        "network_share_remotes",
        "change_folder_source",
        "change_folder_credential",
        "choose_folder",
        "workspace_menu_actions",
        "browse_hub_folder",
        "show_picker_folder",
        "open_picker_folder",
        "refresh_folder_actions",
        "delete_picker_folder",
    )
    FIELDS = (
        "_folder_opening",
        "_folder_opening_name",
        "_hub_refreshing",
        "folder_action_controls",
        "folder_add_share_button",
        "folder_add_remote_button",
        "folder_configured_sources",
        "folder_browse_button",
        "folder_buttons",
        "folder_collapsed",
        "folder_credential",
        "folder_credential_name",
        "folder_credential_row",
        "folder_credentials",
        "folder_list",
        "folder_loading_progress",
        "folder_loading_box",
        "folder_loading_status",
        "folder_picker_choices",
        "folder_picker_view",
        "folder_source_styled",
        "folder_picker_header",
        "folder_picker_selected",
        "folder_picker_status",
        "folder_source",
        "folder_source_buttons",
        "folder_source_actions",
        "folder_source_tabs",
        "folder_tab_views",
        "folder_tab_snapshot",
        "folder_transfers_button",
        "folder_tree_buttons",
        "hub_crypt_locations",
        "hub_crypt_roots",
    )

    def __init__(self, app):
        self.app = app
        self.discovery = FolderDiscovery(
            FolderDiscoveryHost(
                loop=app.loop,
                active=lambda: self.active_host,
                stamp=self.discovery_stamp,
                snapshot=self.discovery_snapshot,
                publish=self.publish_discovery,
                error=self.discovery_error,
            )
        )

    def discovery_stamp(self):
        client = getattr(self, "cloud_client", None)
        return id(client), getattr(client, "generation", None)

    def discovery_snapshot(self):
        from features.rclone.transfers.mobile.jobs import resolved_job

        client = getattr(self, "cloud_client", None)
        return FolderDiscoverySnapshot(
            private_root=self.private_root,
            jobs=deepcopy(
                {
                    key: resolved_job(client, job)
                    for key, job in self.mirror_store().jobs.items()
                }
            ),
            remote_names=tuple(self.loaded_remote_names()),
            retained_packages=tuple(deepcopy(self.retained_credential_associations())),
            crypt_locations=tuple(getattr(self, "hub_crypt_locations", ())),
            crypt_roots=deepcopy(getattr(self, "hub_crypt_roots", {})),
            source_packages=tuple(deepcopy(getattr(client, "package_records", ()))),
        )

    def publish_discovery(self, result):
        self.hub_crypt_locations = list(result.crypt_locations)
        if hasattr(self, "folder_list"):
            self.update_folder_list(result.choices)

    def discovery_error(self, message):
        self.folder_hub_error = message[:300]
        if hasattr(self, "folder_loading_status"):
            self.set_folder_loading("Refresh failed: " + self.folder_hub_error)

    _impl = HostAttribute("_impl")
    active_host = HostAttribute("active_host")
    adaptive = HostAttribute("adaptive")
    browse_cloud = HostService("browse_cloud")
    browser_file_location = HostAttribute("browser_file_location")
    cancel_cloud = HostService("cancel_cloud")
    cancel_mirror_transfer = HostAttribute("cancel_mirror_transfer")
    clear_private_reader = HostService("clear_private_reader")
    cloud_busy = HostAttribute("cloud_busy")
    cloud_client = HostAttribute("cloud_client")
    cloud_location = HostAttribute("cloud_location")
    cloud_open_remote = HostAttribute("cloud_open_remote")
    cloud_path = HostAttribute("cloud_path")
    cloud_remote = HostAttribute("cloud_remote")
    credential_groups = HostService("credential_groups")
    crypt_folder_target = HostAttribute("crypt_folder_target")
    delete_mirror_copy = HostAttribute("delete_mirror_copy")
    existing_crypt_locations = HostAttribute("existing_crypt_locations")
    folder_hub_error = HostAttribute("folder_hub_error")
    loaded_remote_names = HostService("loaded_remote_names")
    main_window = HostAttribute("main_window")
    mirror_store = HostAttribute("mirror_store")
    native_host = HostAttribute("native_host")
    navigation_generation = HostAttribute("navigation_generation")
    open_mirror_copy = HostAttribute("open_mirror_copy")
    preferences = HostAttribute("preferences")
    private_root = HostAttribute("private_root")
    pull_remote_copy = HostAttribute("pull_remote_copy")
    readers = HostAttribute("readers")
    register_transfer_status = HostAttribute("register_transfer_status")
    remote_activity = HostService("remote_activity")
    remote_read_busy = HostAttribute("remote_read_busy")
    require_remote_credentials_async = HostService("require_remote_credentials_async")
    retained_credential_associations = HostService("retained_credential_associations")
    routes = HostAttribute("routes")
    session_credential_packages = HostAttribute("session_credential_packages")
    set_cloud_busy = HostService("set_cloud_busy")
    show_cloud = HostService("show_cloud")
    start_cloud_restore = HostAttribute("start_cloud_restore")
    show_cloud_connections = HostService("show_cloud_connections")
    show_files = HostAttribute("show_files")
    show_legacy_session = HostAttribute("show_legacy_session")
    show_local_push = HostAttribute("show_local_push")
    show_locations = HostService("show_locations")
    show_smb_connection = HostService("show_smb_connection")
    show_transfers = HostAttribute("show_transfers")
    show_view = HostService("show_view")
    show_window_boundary = HostAttribute("show_window_boundary")
    start_mirror_pull = HostAttribute("start_mirror_pull")
    start_mirror_review = HostAttribute("start_mirror_review")
    transfer_busy = HostAttribute("transfer_busy")
    window_id = HostAttribute("window_id")
