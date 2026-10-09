"""Asynchronous file lifecycle; all dialogs and buffer updates run on the GUI thread."""

from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.text_files import (
    read_text_file,
    write_text_file,
    decode_bytes,
    FileConflictError,
    MAX_BYTES,
)
from .document import Document


class FileOperations:
    def _run(self, work, done, failed=None, *, message="Working…"):
        if self.task.busy:
            self._queue.append(lambda: self._run(work, done, failed, message=message))
            return
        self._done = done
        self._failed = failed
        self.task.start(lambda report, cancelled: work(), message=message)
        self._update_actions()

    def _finished(self, result, error):
        done, failed = self._done, self._failed
        self.task.hide()
        if error:
            if failed:
                failed(error)
            else:
                self.show_error(error)
        else:
            done(result)
        self._update_actions()
        if self._queue and not self.task.busy:
            action = self._queue.pop(0)
            action()
        elif self._close_pending and not self.task.busy:
            self._close_pending = False
            self.close()
        self.idle.emit()

    def new_document(self):
        return self._add_document(Document())

    def _add_document(self, document):
        index = self.tabs.addTab(document, document.title)
        self.tabs.setCurrentIndex(index)
        self.tabs.setTabToolTip(
            index, str(document.path) if document.path else "Unsaved new document"
        )
        document.changed.connect(lambda: self._document_changed(document))
        self._configure_document(document)
        self._document_changed(document)
        document.editor.setFocus()
        return document

    def open_dialog(self, force=False):
        paths, _ = qt.QFileDialog.getOpenFileNames(
            self,
            "Open text files",
            str(self.current.path.parent) if self.current and self.current.path else "",
            "All files (*)",
        )
        for path in paths:
            self.open_path(path, force=force)

    def open_path(self, path, *, force=False, encoding=None):
        path = Path(path).resolve()
        for doc in self.documents:
            if doc.path == path:
                self.tabs.setCurrentWidget(doc)
                self.show()
                self.raise_()
                return doc

        def loaded(snapshot):
            # Requests can be queued; canonical paths are checked again on arrival.
            if any(doc.path == path for doc in self.documents):
                self.tabs.setCurrentWidget(
                    next(doc for doc in self.documents if doc.path == path)
                )
                return
            document = Document(snapshot)
            if document.simple:
                qt.QMessageBox.information(
                    self,
                    "Large text file",
                    "This file opens in simple mode: syntax and occurrence highlighting are disabled. Files over 16 MiB are refused.",
                )
            self._add_document(document)
            self._remember_path(path)
            self._watch_paths()

        def failed(error):
            if "binary file" in error and not force:
                answer = qt.QMessageBox.warning(
                    self,
                    "Likely binary file",
                    error,
                    qt.QMessageBox.StandardButton.Open
                    | qt.QMessageBox.StandardButton.Cancel,
                    qt.QMessageBox.StandardButton.Cancel,
                )
                if answer == qt.QMessageBox.StandardButton.Open:
                    self.open_path(path, force=True, encoding=encoding)
            elif ("decode" in error or "codec" in error) and encoding is None:
                from commonUtils.text_files import ENCODINGS

                choice, accepted = qt.QInputDialog.getItem(
                    self,
                    "Choose file encoding",
                    "Decoding failed. Select the original encoding (no replacement characters will be inserted):",
                    ENCODINGS,
                    0,
                    False,
                )
                if accepted:
                    self.open_path(path, force=force, encoding=choice)
            else:
                self.show_error(error)

        self._run(
            lambda: read_text_file(path, encoding=encoding, force=force),
            loaded,
            failed,
            message=f"Opening {path.name}…",
        )
        self.show()
        self.raise_()
        return None

    def save_document(self, document=None, *, save_as=False, after=None):
        document = document or self.current
        if document is None or self.task.busy:
            return False
        path = document.path
        expected = document.snapshot.original if path else None
        overwrite = False
        destination_stamp = None
        if save_as or path is None:
            name, _ = qt.QFileDialog.getSaveFileName(
                self,
                "Save text file",
                str(path) if path else "Untitled.txt",
                "All files (*)",
            )
            if not name:
                return False
            path = Path(name).resolve()
            if any(
                other is not document and other.path == path for other in self.documents
            ):
                self.show_error("That file is already open in another tab.")
                return False
            expected = document.snapshot.original if path == document.path else None
            if path.exists() and expected is None:
                choice = qt.QMessageBox.question(
                    self,
                    "Replace existing file?",
                    str(path),
                    qt.QMessageBox.StandardButton.Yes
                    | qt.QMessageBox.StandardButton.Cancel,
                    qt.QMessageBox.StandardButton.Cancel,
                )
                if choice != qt.QMessageBox.StandardButton.Yes:
                    return False
                # Save As also protects changes occurring after confirmation.
                try:
                    info = path.stat()
                except OSError as error:
                    self.show_error(str(error))
                    return False
                if info.st_size > MAX_BYTES:
                    self.show_error(
                        "The destination exceeds the 16 MiB limit. Choose another file."
                    )
                    return False
                destination_stamp = (
                    info.st_mtime_ns,
                    info.st_ctime_ns,
                    info.st_size,
                    info.st_ino,
                )
                overwrite = True
        snapshot = document.snapshot
        text = document.editor.toPlainText()
        encoding = document.encoding
        newline = document.newline_override
        bom = document.bom_override

        def write():
            target_expected = expected
            if destination_stamp is not None:
                info = path.stat()
                if (
                    info.st_mtime_ns,
                    info.st_ctime_ns,
                    info.st_size,
                    info.st_ino,
                ) != destination_stamp:
                    raise FileConflictError(
                        "The destination changed after confirmation."
                    )
                with path.open("rb") as stream:
                    target_expected = stream.read(MAX_BYTES + 1)
                if len(target_expected) > MAX_BYTES:
                    raise FileConflictError(
                        "The destination changed after confirmation."
                    )
            content = snapshot.encode(text, encoding=encoding, newline=newline, bom=bom)
            write_text_file(
                path, content, expected=target_expected, allow_overwrite=overwrite
            )
            return content

        previous_readonly = document.editor.isReadOnly()
        document.editor.setReadOnly(True)

        def done(content):
            document.editor.setReadOnly(previous_readonly)
            document.snapshot = decode_bytes(
                content, path=path, encoding=encoding, force=True
            )
            document.encoding = document.snapshot.encoding
            document.newline_override = None
            document.bom_override = None
            document.external_changed = False
            document.external_acknowledged = False
            document.editor.document().setModified(False)
            document.changed.emit()
            self._remember_path(path)
            self._watch_paths()
            self.statusBar().showMessage("Saved.", 3000)
            self.saved.emit(path)
            if after:
                after()

        def failed(error):
            document.editor.setReadOnly(previous_readonly)
            self.show_error(error)

        self._run(write, done, failed, message=f"Saving {path.name}…")
        return True

    def save_all(self):
        pending = [doc for doc in self.documents if doc.modified or doc.path is None]

        def step():
            if pending:
                self.save_document(pending.pop(0), after=step)

        step()

    def reload_document(self):
        document = self.current
        if document is None or document.path is None or self.task.busy:
            return
        if (
            document.modified
            and qt.QMessageBox.question(
                self,
                "Reload from disk?",
                "Discard the current buffer and reload? This cannot be undone.",
                qt.QMessageBox.StandardButton.Discard
                | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel,
            )
            != qt.QMessageBox.StandardButton.Discard
        ):
            return
        self._run(
            lambda: read_text_file(document.path, encoding=document.encoding),
            lambda snapshot: (
                document.replace(snapshot),
                self._configure_document(document),
                self._watch_paths(),
            ),
            message="Reloading from disk…",
        )

    def close_tab(self, index, *, after=None):
        if self.task.busy or self._queue:
            return False
        document = self.tabs.widget(index)
        if document is None:
            return True
        if document.modified:
            self.tabs.setCurrentIndex(index)
            answer = qt.QMessageBox.question(
                self,
                "Unsaved text changes",
                f"Save changes to {document.title}?",
                qt.QMessageBox.StandardButton.Save
                | qt.QMessageBox.StandardButton.Discard
                | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel,
            )
            if answer == qt.QMessageBox.StandardButton.Cancel:
                return False
            if answer == qt.QMessageBox.StandardButton.Save:
                self.save_document(
                    document,
                    after=lambda: self.close_tab(
                        self.tabs.indexOf(document), after=after
                    ),
                )
                return False
        self.tabs.removeTab(index)
        document.deleteLater()
        self._watch_paths()
        if after:
            after()
        return True

    def close_all(self):
        if self.tabs.count():
            self.close_tab(self.tabs.count() - 1, after=self.close_all)

    def prepare_close(self):
        if self.task.busy or self._queue:
            return False
        if hasattr(self, "search") and not self.search.prepare_close():
            return False
        for index in range(self.tabs.count() - 1, -1, -1):
            if not self.close_tab(index):
                return False
        return True

    def _watch_paths(self):
        watched = self.watcher.files()
        if watched:
            self.watcher.removePaths(watched)
        paths = [
            str(doc.path) for doc in self.documents if doc.path and doc.path.exists()
        ]
        if paths:
            self.watcher.addPaths(paths)

    def _remember_path(self, path):
        try:
            self.recent.add(path)
        except OSError:
            self.statusBar().showMessage(
                "The file is open; recent-file history could not be updated.", 5000
            )

    def _external_change(self, path):
        for document in self.documents:
            if document.path and str(document.path) == path:
                document.external_changed = True
                document.external_acknowledged = False
                self.external_notice.setText(
                    "File changed or was deleted on disk. Reload to discard this buffer, or Keep Buffer and use Save As. Saving rejects conflicting disk contents."
                )
                self._document_changed(document)
                if document is self.current:
                    self.external_bar.show()
        self._watch_paths()
