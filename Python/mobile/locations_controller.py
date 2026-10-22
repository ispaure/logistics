"""Owned workflow state and explicit application services."""
from services.workflow_host import HostAttribute
from mobile.locations_ui import LocationsUI


class LocationsController(LocationsUI):
    METHODS = ('pinned_locations', 'pin_local_folder', 'pin_remote_folder', 'pinned_opener', 'pinned_remover')
    FIELDS = ('location_error', 'locations')

    def __init__(self, app):
        self.app = app

    active_host = HostAttribute('active_host')
    browser_cloud_location = HostAttribute('browser_cloud_location')
    browser_file_location = HostAttribute('browser_file_location')
    cloud_busy = HostAttribute('cloud_busy')
    cloud_client = HostAttribute('cloud_client')
    cloud_crypt_remotes = HostAttribute('cloud_crypt_remotes')
    cloud_open_remote = HostAttribute('cloud_open_remote')
    cloud_path = HostAttribute('cloud_path')
    cloud_remote = HostAttribute('cloud_remote')
    cloud_restore_task = HostAttribute('cloud_restore_task')
    cloud_status = HostAttribute('cloud_status')
    file_path = HostAttribute('file_path')
    file_status = HostAttribute('file_status')
    file_storage = HostAttribute('file_storage')
    private_root = HostAttribute('private_root')
    show_cloud = HostAttribute('show_cloud')
    show_local_location = HostAttribute('show_local_location')
    show_locations = HostAttribute('show_locations')
