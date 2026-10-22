"""Owned workflow state and explicit application services."""

from services.workflow_host import HostAttribute
from mobile.storage_ui import StorageUI
from mobile.reset_ui import ResetUI


class StorageController(StorageUI, ResetUI):
    METHODS = (
        "open_android_developer_settings",
        "show_collection_storage",
        "allow_collection_storage",
        "change_collection_storage",
        "recover_collection_storage",
        "wipe_collection_storage",
        "start_empty_collection",
        "collection_target_changed",
        "show_app_reset",
        "reset_phrase_changed",
        "confirm_app_reset",
    )
    FIELDS = (
        "collection_storage_progress_view",
        "_storage_changing",
        "collection_drive",
        "collection_drives",
        "collection_storage_status",
        "collection_storage_page",
        "collection_target_status",
        "collection_copy",
        "collection_existing",
        "collection_empty",
        "collection_erase",
        "reset_phrase",
        "reset_button",
        "reset_status",
        "reset_page",
    )

    def __init__(self, app):
        self.app = app

    _impl = HostAttribute("_impl")
    checkpoint = HostAttribute("checkpoint")
    cloud_busy = HostAttribute("cloud_busy")
    exit = HostAttribute("exit")
    main_window = HostAttribute("main_window")
    private_root = HostAttribute("private_root")
    set_cloud_busy = HostAttribute("set_cloud_busy")
    show_cloud = HostAttribute("show_cloud")
    show_view = HostAttribute("show_view")
    transfer_busy = HostAttribute("transfer_busy")
    workspace = HostAttribute("workspace")
