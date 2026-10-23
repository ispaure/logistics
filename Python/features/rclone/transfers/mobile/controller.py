"""Owned workflow state and explicit application services."""
from services.workflow_host import HostAttribute, StateAttribute
from features.rclone.transfers.mobile.ui import MirrorUI, TransferExecutionPresentation
from .execution import TransferExecution, TransferState


class TransferController(MirrorUI):
    METHODS = ('register_transfer_status', 'dismiss_transfer_status', 'refresh_transfer_status', 'existing_crypt_locations', 'crypt_folder_target', 'linked_crypt_locations', 'mirror_store', 'show_transfers', 'choose_transfer_copy', 'delete_mirror_copy', 'mirror_connection_ready', 'start_mirror_pull', 'mirror_job_signature', 'start_mirror_review', 'pull_remote_copy', 'push_remote_copy', 'run_mirror_work', 'publish_mirror_progress', 'cancel_mirror_transfer', 'open_mirror_copy', 'show_local_push', 'transfer_options', 'show_transfer_options', 'begin_transfer_review', 'review_transfer', '_review_transfer')
    FIELDS = ('_cancel_transfer_review', '_mirror_progress_widgets', '_review_starting', '_transfer_cancel', '_transfer_review_view', 'file_roots', 'mirrors', 'transfer_banners', 'transfer_busy', 'transfer_complete', 'transfer_endpoints', 'transfer_epoch', 'transfer_message', 'transfer_notice', 'transfer_notification', 'transfer_progress', 'transfer_task', 'transfer_view')

    FIELDS += ('transfer_percentage',)

    def __init__(self, app):
        self.app = app
        self.state = TransferState()
        self.execution = TransferExecution(self.state, TransferExecutionPresentation(self))
        self._transfer_cancel = None
        self._cancel_transfer_review = None

    transfer_busy = StateAttribute("state", "busy")
    transfer_notification = StateAttribute("state", "notification")
    transfer_complete = StateAttribute("state", "complete")
    transfer_percentage = StateAttribute("state", "percentage")
    transfer_epoch = StateAttribute("state", "epoch")
    transfer_message = StateAttribute("state", "message")
    transfer_endpoints = StateAttribute("state", "endpoints")
    _transfer_cancel = StateAttribute("state", "cancel")

    active_host = HostAttribute('active_host')
    browser_file_location = HostAttribute('browser_file_location')
    clear_private_reader = HostAttribute('clear_private_reader')
    cloud_busy = HostAttribute('cloud_busy')
    cloud_client = HostAttribute('cloud_client')
    cloud_crypt_remotes = HostAttribute('cloud_crypt_remotes')
    cloud_entries = HostAttribute('cloud_entries')
    cloud_open_remote = HostAttribute('cloud_open_remote')
    cloud_path = HostAttribute('cloud_path')
    cloud_restore_task = HostAttribute('cloud_restore_task')
    cloud_rows = HostAttribute('cloud_rows')
    cloud_status = HostAttribute('cloud_status')
    cloud_transfer_progress = HostAttribute('cloud_transfer_progress')
    file_provider = HostAttribute('file_provider')
    file_status = HostAttribute('file_status')
    files_view = HostAttribute('files_view')
    loaded_remote_names = HostAttribute('loaded_remote_names')
    loop = HostAttribute('loop')
    main_window = HostAttribute('main_window')
    native_host = HostAttribute('native_host')
    navigation_generation = HostAttribute('navigation_generation')
    private_root = HostAttribute('private_root')
    rclone_ui = HostAttribute('rclone_ui')
    remote_activity = HostAttribute('remote_activity')
    require_remote_credentials_async = HostAttribute('require_remote_credentials_async')
    routes = HostAttribute('routes')
    selected_cloud_remote = HostAttribute('selected_cloud_remote')
    set_cloud_busy = HostAttribute('set_cloud_busy')
    show_cloud = HostAttribute('show_cloud')
    show_local_location = HostAttribute('show_local_location')
    show_locations = HostAttribute('show_locations')
    show_view = HostAttribute('show_view')
    update_file_locations = HostAttribute('update_file_locations')
