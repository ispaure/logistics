"""Owned comic folder batches; host services supply storage, lifecycle and routing."""

import asyncio
import threading
from commonUtils.runtime.resources.local import LocalFiles
from services.workflow_host import HostAttribute


class ComicBatchController:
    METHODS = (
        "edit_local_comic_folder",
        "retire_private_comic_batch",
        "edit_private_comic_folder",
    )
    FIELDS = ("local_comic_batch", "local_comic_batch_view", "private_comic_batch")

    def __init__(self, app):
        self.app = app
        self.local_comic_batch = None
        self.local_comic_batch_view = None
        self.private_comic_batch = None

    active_host = HostAttribute("active_host")
    cloud_busy = HostAttribute("cloud_busy")
    cloud_client = HostAttribute("cloud_client")
    file_action_status = HostAttribute("file_action_status")
    file_path = HostAttribute("file_path")
    file_provider = HostAttribute("file_provider")
    file_rows = HostAttribute("file_rows")
    file_selection = HostAttribute("file_selection")
    main_window = HostAttribute("main_window")
    navigation_generation = HostAttribute("navigation_generation")
    scene_manager = HostAttribute("scene_manager")
    screen_privacy = HostAttribute("screen_privacy")
    set_cloud_busy = HostAttribute("set_cloud_busy")
    show_files = HostAttribute("show_files")
    show_view = HostAttribute("show_view")

    async def edit_local_comic_folder(self, widget=None, **kwargs):
        if self.cloud_busy:
            return
        if self.file_provider.private:
            return await self.edit_private_comic_folder()
        from features.comics.collection import (
            scan_comics,
            CollectionBatch,
            suggestions,
            open_local_comic,
        )
        from features.comics.collection.metadata import metadata_fields
        from features.comics.mobile.metadata import batch_form

        provider = self.file_provider
        if not isinstance(provider, LocalFiles) or provider.private:
            return
        selected = self.file_rows.get(self.file_selection.value)
        folder = (
            selected["path"] if selected and selected["directory"] else self.file_path
        )
        cancel = threading.Event()
        self.set_cloud_busy(True)
        try:

            def prepare():
                entries = scan_comics(provider, folder, cancelled=cancel.is_set)
                if not entries:
                    raise ValueError("No CBZ/ZIP comics found in this folder.")

                def document(path):
                    return open_local_comic(provider._locate(path))

                return CollectionBatch(
                    entries,
                    open_document=document,
                    revision=lambda path: provider.entry(path)["revision"],
                    publish=lambda path, doc, changes: doc.save(changes),
                )

            plan = await asyncio.to_thread(prepare)
        except Exception as error:
            self.file_action_status.text = "Cannot edit folder: " + str(error)[:200]
            return
        finally:
            self.set_cloud_busy(False)

        async def apply(changes):
            if self.cloud_busy:
                return "Wait for the current operation."
            if not changes:
                return "No fields selected."
            self.set_cloud_busy(True)
            cancel.clear()
            try:
                completed, failures = await asyncio.to_thread(
                    plan.apply, changes, cancelled=cancel.is_set
                )
                return (
                    f"{len(completed)} saved; {len(failures)} failed; "
                    f"{len(plan.entries) - len(completed) - len(failures)} unprocessed. "
                    + " ".join(message for _, message in failures)[:300]
                )
            finally:
                self.set_cloud_busy(False)

        choices = suggestions(
            metadata_fields(document) for document in plan.documents
        )

        async def back(widget=None, **kwargs):
            await self.show_files()

        view = batch_form(
            plan.documents,
            save=apply,
            choices=choices,
            width=max(1, min(640, min(self.main_window.size) - 24)),
            cancel=lambda w, **kw: cancel.set(),
            back=back,
        )
        self.local_comic_batch, self.local_comic_batch_view = plan, view
        self.show_view(
            view,
            destination="files",
            route="comic-folder-batch",
            title="Edit folder comics",
        )

    def retire_private_comic_batch(self, *, view=None, stale_only=False):
        plan = getattr(self, "private_comic_batch", None)
        if plan is None or (view is not None and plan.view is view):
            return
        if stale_only and plan.valid():
            return
        plan.close()
        self.private_comic_batch = None
        privacy = getattr(self, "screen_privacy", None)
        if privacy is not None:
            privacy.refresh()

    async def edit_private_comic_folder(self):
        from contextlib import contextmanager
        from features.rclone.localcrypt.mobile.resources import (
            CryptFiles,
            encrypted_document,
        )
        from features.comics.mobile.private_batch import PrivateCollectionBatch
        from features.comics.collection.metadata import metadata_fields
        from features.comics.collection import suggestions
        from features.comics.mobile.metadata import batch_form
        from commonUtils.runtime.operations import OperationCancelled

        provider = self.file_provider
        if not isinstance(provider, CryptFiles) or self.cloud_busy:
            return
        if len(self.scene_manager.owners.hosts) > 1:
            self.file_action_status.text = (
                "Close other windows before editing private collections."
            )
            return
        self.retire_private_comic_batch()
        client, generation = self.cloud_client, self.cloud_client.generation
        navigation = self.navigation_generation

        def valid():
            return (
                self.active_host
                and self.cloud_client is client
                and client.generation == generation
                and getattr(self, "private_comic_batch", None) is plan
            )

        def release(reader):
            source = reader.source
            if hasattr(source, "close"):
                source.close()
            if hasattr(source, "data"):
                source.data = b""
            reader.data, reader.password = None, ""
            reader.book = None
            reader.__dict__.pop("_comic", None)

        @contextmanager
        def opened(path):
            copies, key = encrypted_document(provider, path)
            reader = copies.open(
                key,
                cancelled=lambda: plan.closed or plan.cancel.is_set() or not valid(),
            )
            try:
                yield reader
            finally:
                release(reader)

        def publish(reader, changes, *, cancelled):
            copies, _ = encrypted_document(provider, reader.key)
            return copies.save_metadata(reader, changes, cancelled=cancelled)

        plan = PrivateCollectionBatch(
            valid=valid,
            open_reader=opened,
            revision=lambda path: provider.entry(path)["revision"],
            publish=publish,
            release_reader=release,
        )
        self.private_comic_batch = plan
        plan.privacy_gate = getattr(client, "session_privacy", None)
        self.screen_privacy.refresh()
        selected = self.file_rows.get(self.file_selection.value)
        folder = (
            selected["path"] if selected and selected["directory"] else self.file_path
        )
        self.set_cloud_busy(True)
        try:
            await asyncio.to_thread(plan.prepare, provider, folder)
            if not valid() or self.navigation_generation != navigation:
                self.retire_private_comic_batch()
                return

            async def save(changes):
                if (
                    self.cloud_busy
                    or not valid()
                    or plan.closed
                    or plan.requires_reopen
                ):
                    return "Private batch is unavailable. Reopen the folder."
                if not changes:
                    return "No fields selected."
                plan.cancel.clear()
                self.set_cloud_busy(True)
                count = len(plan.entries)
                try:
                    completed, failures = await asyncio.to_thread(plan.apply, changes)
                    message = f"{len(completed)} saved encrypted locally; {len(failures)} failed; {count - len(completed) - len(failures)} unprocessed."
                    if plan.requires_reopen:
                        message += " A file may already be saved. Reopen the batch before retrying."
                    return message
                finally:
                    self.set_cloud_busy(False)

            async def back(widget=None, **kwargs):
                self.retire_private_comic_batch()
                await self.show_files()

            choices = suggestions(
                metadata_fields(document) for document in plan.documents
            )
            view = batch_form(
                plan.documents,
                save=save,
                back=back,
                choices=choices,
                width=max(1, min(640, min(self.main_window.size) - 24)),
                cancel=lambda w, **kw: plan.cancel.set(),
            )
            plan.view = view
            self.show_view(
                view,
                destination="files",
                route="private-comic-batch",
                title="Edit private folder comics",
            )
        except OperationCancelled:
            self.retire_private_comic_batch()
        except Exception:
            self.retire_private_comic_batch()
            self.file_action_status.text = "Private batch could not be opened. Check the folder, credentials and archive passwords."
        finally:
            self.set_cloud_busy(False)
