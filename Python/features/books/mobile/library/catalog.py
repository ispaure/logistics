"""Books & Comics discovery and inventory with explicit host services."""

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from typing import Callable
from features.comics.mobile.collection.imported import ImportedComicBatch

from .catalog_panel import LibraryCatalogPanel


@dataclass(frozen=True)
class LibraryHost:
    presentation: object
    folder_visible: Callable
    show_locations: Callable
    open_folder: Callable
    snapshot: Callable
    discover: Callable


class LibraryCatalog(ImportedComicBatch, LibraryCatalogPanel):
    def clear_private_libraries(self):
        self.library_scan_epoch = getattr(self, "library_scan_epoch", 0) + 1
        self.library_records = [
            record
            for record in getattr(self, "library_records", ())
            if not record["provider"].private
        ]
        self.filter_library()

    async def refresh_library_folders(self, widget=None, **kwargs):
        """Serialize discovery and briefly reuse the same credential/config snapshot."""
        while True:
            task = getattr(self, "_library_discovery", None)
            if task is not None and not task.done():
                await asyncio.shield(task)
                if not self.active_host:
                    return
                continue
            client, jobs, remotes = self.library_host.snapshot()
            signature = (
                id(client),
                getattr(client, "generation", None),
                json.dumps(jobs, sort_keys=True),
                tuple(sorted(remotes)),
                getattr(self, "_library_discovery_revision", 0),
            )
            cached = getattr(self, "_library_discovery_cached", None)
            if (
                widget is None
                and cached is not None
                and cached[0] == signature
                and self.loop.time() - cached[1] < 2
            ):
                return
            self._library_discovery = task = self.loop.create_task(
                self._discover_library_folders()
            )
            await asyncio.shield(task)
            if (
                self.active_host
                and client is self.library_host.snapshot()[0]
                and signature[1] == getattr(client, "generation", None)
            ):
                self._library_discovery_cached = signature, self.loop.time()
            return

    async def _discover_library_folders(self):
        epoch = self.library_scan_epoch = getattr(self, "library_scan_epoch", 0) + 1
        client, jobs, remotes = self.library_host.snapshot()
        generation = getattr(client, "generation", None)
        self.book_status.text = "Finding configured libraries…"
        try:
            records, failures = await asyncio.to_thread(
                self.library_host.discover, self.private_root, jobs, client, remotes
            )
        except (OSError, ValueError):
            records, failures = [], 1
        if not self.active_host or epoch != self.library_scan_epoch:
            return
        if client is not self.library_host.snapshot()[0] or generation != getattr(
            client, "generation", None
        ):
            records = [record for record in records if not record["provider"].private]
        for record in records:
            record.update(client=client, generation=generation)
        self.library_records = records
        self.filter_library()
        self.book_status.text = (
            f"{failures} library configuration(s) could not be read."
            if failures
            else f"{len(records)} configured library folder(s)."
        )

    def refresh_library(self, widget=None, **kwargs):
        if widget is not None:
            self._library_discovery_revision = (
                getattr(self, "_library_discovery_revision", 0) + 1
            )
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._publish_library_inventory(*self.library_store.items())
            return
        self._publish_library_inventory(*self.library_store.cached_items())
        self._library_refresh_again = True
        task = getattr(self, "_library_inventory_task", None)
        if task is None or task.done():

            async def refresh():
                while self.active_host and self._library_refresh_again:
                    self._library_refresh_again = False
                    records, failures = await asyncio.to_thread(
                        self.library_store.items
                    )
                    if self.active_host and not self._library_refresh_again:
                        self._publish_library_inventory(records, failures)

            self._library_inventory_task = self.loop.create_task(refresh())

    def _publish_library_inventory(self, records, failures):
        from services.mobile_features import document_feature, enabled
        records = [record for record in records
            if enabled(self.preferences, document_feature(record['name'], record['kind']))]
        previous = self.book_loading
        self.book_loading = True
        self.imported_records = records
        if hasattr(self, "library_rows"):
            self.refresh_imported_metadata(records)
        labels = {}
        for record in records:
            label = record["name"]
            while label in labels:
                label += " (copy)"
            labels[label] = record["id"]
        if hasattr(self, "library_rows"):
            self.library_scan_task = self.loop.create_task(
                self.refresh_library_folders()
            )
        self.book_labels = labels
        self.book_selector.items = list(labels)
        if self.book_record:
            self.book_selector.value = next(
                (
                    label
                    for label, key in labels.items()
                    if key == self.book_record["id"]
                ),
                None,
            )
        if failures:
            self.book_status.text = f"{len(failures)} library record(s) could not be read; they were preserved."
        self.book_loading = previous

    async def wait_for_refresh(self):
        """Wait for inventories and the metadata work they schedule, not an old scan."""
        while True:
            inventory = getattr(self, "_library_inventory_task", None)
            if inventory is not None:
                await asyncio.shield(inventory)
            discovery = getattr(self, "library_scan_task", None)
            metadata = getattr(self, "metadata_task", None)
            for task in (discovery, metadata):
                if task is not None:
                    await asyncio.shield(task)
            if (
                inventory is getattr(self, "_library_inventory_task", None)
                and discovery is getattr(self, "library_scan_task", None)
                and metadata is getattr(self, "metadata_task", None)
            ):
                return

    def refresh_imported_metadata(self, records):
        epoch = self.metadata_epoch = getattr(self, "metadata_epoch", 0) + 1
        records = [dict(record) for record in records]
        self.imported_selected.intersection_update(record["id"] for record in records)
        self.metadata_ready = False
        self.filter_library()
        from features.books.library.index import CollectionIndex

        if not hasattr(self, "metadata_index"):
            self.metadata_index = CollectionIndex(
                self.library_store.root / ".metadata.sqlite3"
            )

        def current():
            return (
                self.metadata_epoch == epoch
                and self.active_host
                and not self.loop.is_closed()
            )

        def signature(record):
            path = self.library_store.path(
                record["id"], ".epub" if record["kind"] == "epub" else ".cbz"
            )
            info = path.stat()
            return (
                info.st_dev,
                info.st_ino,
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
            )

        def load(record):
            from features.books.library.metadata import metadata_fields

            path = self.library_store.path(
                record["id"], ".epub" if record["kind"] == "epub" else ".cbz"
            )
            # Never consult passwords or index protected metadata, even when an
            # inner ZIP has a remembered/configured password elsewhere.
            if self.library_store.validate_archive(path, record["kind"]):
                return None
            _, reader = self.library_store.open(record["id"])
            return metadata_fields(record["kind"], reader)

        def report(done, total, failures):
            def update():
                if current():
                    first = not self.metadata_ready
                    self.metadata_ready = True
                    self.library_index_status.text = f"Metadata checked: {done}/{total} imports.\n{failures} unreadable; protected metadata excluded."
                    if first or done == total:
                        self.filter_library()

            if not self.loop.is_closed():
                self.loop.call_soon_threadsafe(update)

        async def scan():
            try:
                await asyncio.to_thread(
                    self.metadata_index.scan,
                    records,
                    signature=signature,
                    load=load,
                    cancelled=lambda: not current(),
                    progress=report,
                )
            except (OSError, ValueError, sqlite3.Error):
                if current():
                    self.library_index_status.text = (
                        "Metadata index unavailable; filename search remains available."
                    )
                    self.metadata_ready = False
                    self.filter_library()
            if current():
                self.filter_library()

        self.metadata_task = self.loop.create_task(scan())
