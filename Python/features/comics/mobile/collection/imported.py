"""Imported comic batch presentation; storage publication is injected by the reader host."""

import asyncio


class ImportedComicBatch:
    async def edit_imported_comics(self, widget=None, **kwargs):
        if self.book_busy:
            return
        selected = [
            record
            for record in self.imported_records
            if record["id"] in self.imported_selected
        ]
        if not selected:
            self.book_status.text = "Select comics before opening batch metadata."
            return
        if len(selected) > 200:
            self.book_status.text = "Select at most 200 comics per batch."
            return
        self.set_book_busy(True)
        try:
            documents = []
            for record in selected:
                _, reader = await asyncio.to_thread(
                    self.library_store.open, record["id"]
                )
                documents.append(reader.document)
        except Exception as error:
            self.book_status.text = "Cannot edit selection: " + str(error)[:300]
            return
        finally:
            self.set_book_busy(False)
        from features.comics.mobile.metadata import batch_form
        import threading

        cancel = threading.Event()

        async def save(changes):
            if self.book_busy:
                return "Wait for the current batch."
            if not changes:
                return "No fields selected."
            self.set_book_busy(True)
            cancel.clear()
            try:
                completed, failures = await asyncio.to_thread(
                    self.library_store.edit_comics,
                    selected,
                    changes,
                    cancelled=cancel.is_set,
                )
                replacements = {record["id"]: record for record in completed}
                selected[:] = [
                    replacements.get(record["id"], record) for record in selected
                ]
                self.refresh_library()
                return (
                    f"{len(completed)} saved; {len(failures)} failed; "
                    f"{len(selected) - len(completed) - len(failures)} unprocessed. "
                    + " ".join(message for _, message in failures)[:500]
                )
            finally:
                self.set_book_busy(False)

        from features.comics.collection import suggestions

        choices = (
            self.metadata_index.suggestions()
            if getattr(self, "metadata_ready", False)
            else suggestions(())
        )
        view = batch_form(
            documents,
            save=save,
            back=self.show_library,
            cancel=lambda widget, **kw: cancel.set(),
            choices=choices,
            width=max(1, min(640, min(self.main_window.size) - 24)),
        )
        self.show_view(view, reader_route="metadata-batch", title="Edit comic metadata")
