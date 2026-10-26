"""Enumerated host services; document attributes remain controller-owned."""


from services.workflow_host import HostService


class ReaderHost:
    async def document_open_failed(self, error, *, remote, key):
        """Translate source-specific failures at the host presentation boundary."""
        import toga
        self.cloud_status.value = 'Document opening failed: ' + str(error)[:300]
        if remote:
            from commonUtils.archives.zip_access import ArchivePasswordError
            if isinstance(error, ArchivePasswordError):
                row = next((row for row in self.app.cloud_rows.values() if row['path'] == key),
                           dict(path=key, directory=False, size=0))
                self.app.show_remote_item_actions(row, password_required=True)
                return
            from features.rclone.remote_policy import LOCAL_COPY_MESSAGE
            await self.main_window.dialog(toga.InfoDialog('Remote preview unavailable',
                str(error)[:200] + '\n\n' + LOCAL_COPY_MESSAGE))
        else:
            await self.main_window.dialog(toga.InfoDialog('Could not open document', str(error)[:300]))

    def document_open_cancelled(self, *, remote):
        self.cloud_status.value = 'Remote opening cancelled.' if remote else 'Document opening cancelled.'

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
    cloud_status = HostService('document_status')
    crypt_password = HostService('document_password')
    transfer_busy = HostService('transfer_busy')
    register_transfer_status = HostService('register_transfer_status')
    refresh_transfer_status = HostService('refresh_transfer_status')
    show_documents_hub = HostService('show_documents_hub')
    show_cloud = HostService('show_cloud')
