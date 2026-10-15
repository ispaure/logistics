"""Enumerated host services; document attributes remain controller-owned."""


class HostService:
    def __init__(self, name):
        self.name = name

    def __get__(self, owner, cls=None):
        return self if owner is None else getattr(owner.app, self.name)


class ReaderHost:
    private_root = HostService('private_root')
    preferences = HostService('preferences')
    loop = HostService('loop')
    workspace = HostService('workspace')
    active_host = HostService('active_host')
    navigation_generation = HostService('navigation_generation')
    native_host = HostService('native_host')
    scene_manager = HostService('scene_manager')
    main_window = HostService('main_window')
    current = HostService('current')
    save_as_source_document = HostService('save_as_source_document')
    cloud_status = HostService('cloud_status')
    crypt_password = HostService('crypt_password')
    transfer_busy = HostService('transfer_busy')
    register_transfer_status = HostService('register_transfer_status')
    refresh_transfer_status = HostService('refresh_transfer_status')
    show_documents_hub = HostService('show_documents_hub')
    show_cloud = HostService('show_cloud')
