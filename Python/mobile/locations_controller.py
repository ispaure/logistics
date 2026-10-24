"""Owned workflow state and explicit application services."""

from services.workflow_host import HostService
from mobile.locations_ui import LocationsUI


class LocationsController(LocationsUI):
    METHODS = (
        "pinned_locations",
        "pin_local_folder",
        "pin_remote_folder",
        "pinned_opener",
        "pinned_remover",
    )
    FIELDS = ("location_error", "locations")

    def __init__(self, app):
        self.app = app

    active_host = HostService("active_host")
    browser_cloud_location = HostService("browser_cloud_location")
    browser_file_location = HostService("browser_file_location")
    cloud_busy = HostService("cloud_busy")
    cloud_client = HostService("cloud_client")
    cloud_crypt_remotes = HostService("cloud_crypt_remotes")
    cloud_open_remote = HostService("cloud_open_remote")
    cloud_path = HostService("cloud_path")
    cloud_remote = HostService("cloud_remote")
    cloud_restore_task = HostService("cloud_restore_task")
    cloud_status = HostService("cloud_status")
    file_path = HostService("file_path")
    file_status = HostService("file_status")
    file_storage = HostService("file_storage")
    private_root = HostService("private_root")
    show_cloud = HostService("show_cloud")
    show_local_location = HostService("show_local_location")
    show_locations = HostService("show_locations")
