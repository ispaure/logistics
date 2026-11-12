"""Native transfer transport and progress worker; the coordinator owns preflight."""

from threading import Event, Thread
from uuid import uuid4
from features.rclone.mobile.bridge_protocol import mirror_progress, validate_result
from features.rclone.transfers.transfer_options import TransferOptions, DEFAULT_EXCLUDES


def sync_copy(
    job, client, *, check, local_path, push, cancelled, progress, options=None, download=None
):
    check(client, job, cancelled)
    run = uuid4().hex
    done = Event()

    def monitor():
        while not done.wait(0.2):
            if cancelled():
                try:
                    client.cancel()
                except (OSError, ValueError):
                    pass
                return
            try:
                state = mirror_progress(client, run)
                progress(
                    phase=state["phase"] or "Discovering / checking files",
                    files=state.get("files", 0),
                    done=state["done"],
                    total=state["total"],
                    total_files=state.get("total_files", 0),
                    file_delete_attempts=state.get("file_delete_attempts"),
                    folder_removal_attempts=state.get("folder_removal_attempts"),
                    checks=state.get("checks", 0),
                    listed=state.get("listed", 0),
                    active=state.get("active", 0),
                    active_files=state.get("active_files", []),
                    attempt=state.get("attempt", 0),
                    max_attempts=state.get("max_attempts", 0),
                    retrying=state.get("retrying", False),
                )
            except (OSError, ValueError, TypeError, KeyError):
                pass

    watcher = Thread(target=monitor, daemon=True)
    watcher.start()
    try:
        progress(phase="Discovering / checking files", files=0, done=0, total=0)
        check(client, job, cancelled)
        result = client.request(
            "mirror_sync",
            decrypted=not job["crypt"],
            remote=job["remote"],
            path=job["prefix"],
            identity=job["identity"],
            local_path=str(local_path().resolve()),
            run=run,
            push=push,
            **(download or {}),
            **(options or TransferOptions(excludes=DEFAULT_EXCLUDES)).bridge_arguments(
                push=push
            ),
        )
        result = validate_result("mirror_sync", result)
    finally:
        done.set()
        watcher.join()

    try:
        state = mirror_progress(client, run)
    except (OSError, ValueError):
        # Progress is advisory. The sync result and destination checks establish success.
        state = {}
    progress(
        phase="Sync complete; verifying local copy",
        files=result,
        total_files=state.get("total_files", 0),
        file_delete_attempts=state.get("file_delete_attempts"),
        folder_removal_attempts=state.get("folder_removal_attempts"),
        checks=state.get("checks", 0),
        listed=state.get("listed", 0),
        done=state.get("done", 0),
        total=state.get("total", 0),
    )
    return result
