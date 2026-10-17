"""Owned workflow state and explicit application services."""
from services.workflow_host import HostAttribute
from logisticsmobile.storage_ui import StorageUI


class StorageController(StorageUI):
    METHODS = ('open_android_developer_settings', 'show_collection_storage', 'allow_collection_storage', 'change_collection_storage')
    FIELDS = ('_storage_changing', 'collection_drive', 'collection_drives', 'collection_storage_status')

    def __init__(self, app):
        self.app = app

    _impl = HostAttribute('_impl')
    checkpoint = HostAttribute('checkpoint')
    cloud_busy = HostAttribute('cloud_busy')
    exit = HostAttribute('exit')
    main_window = HostAttribute('main_window')
    private_root = HostAttribute('private_root')
    set_cloud_busy = HostAttribute('set_cloud_busy')
    show_cloud = HostAttribute('show_cloud')
    show_view = HostAttribute('show_view')
    transfer_busy = HostAttribute('transfer_busy')
    workspace = HostAttribute('workspace')
