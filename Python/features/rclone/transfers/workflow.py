"""Desktop transfer presentation over the retained rclone service."""
from pathlib import Path
from features.rclone import executable
from features.rclone.desktop_service import service
from .desktop import DesktopTransferRequest
from .service import TransferContext
from .transfer_options import TransferOptions


def reviewed_sync(source, destination, *, operation, config_path, crypt_item=None, before_start=lambda: None, **kwargs):
    return sync_transfer(source, destination, operation=operation, config_path=config_path,
                         crypt_item=crypt_item, before_start=before_start, review=True, **kwargs)


def sync_transfer(source, destination, *, operation, config_path, crypt_item=None, before_start=lambda: None,
                  review=False, **kwargs):
    binary = kwargs.pop('executable_path', None) or executable.ensure_rclone()
    if binary is None:
        return False
    from .push_policy import load_excludes
    options = TransferOptions(track_renames=kwargs.pop('track_renames', False),
        bw_limit=kwargs.pop('bw_limit', None), copy_links=kwargs.pop('copy_links', True),
        excludes=load_excludes() if operation == 'Push' else ())
    cancelled = kwargs.pop('cancelled', lambda: False)
    transfer = DesktopTransferRequest(source=str(source), destination=str(destination), operation=operation,
        config=Path(config_path), binary=Path(binary), options=options, crypt_item=crypt_item,
        before_start=before_start, launch=kwargs)
    if not review:
        return service.transfers.run(transfer, TransferContext(cancelled=cancelled))
    prepared = service.transfers.review(transfer)
    try:
        from .ui.review import confirm_review
        if not confirm_review(prepared):
            return False
        return service.transfers.execute(prepared, TransferContext(cancelled=cancelled))
    finally:
        prepared.review.scan.stop()
