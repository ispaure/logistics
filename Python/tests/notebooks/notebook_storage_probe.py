"""Real Qt canvas + encrypted Save/Save As with disposable synthetic documents."""
import argparse
import json
from pathlib import Path
import time
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from PySide6.QtTest import QTest
from Scripts.build_retention import scratch
from features.notebooks.notebook import Notebook, MAX_ARCHIVE
from features.notebooks.ui.workspace import open_workspace
from features.rclone import executable
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice
from services.documents.storage import DocumentResource
from local_crypt_fixture import crypt_fixture


def main(output):
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    def wait(predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            QTest.qWait(20)
        raise TimeoutError('Qt notebook state did not arrive')
    def evaluate(web, script):
        answer = []
        web.page().runJavaScript(script, lambda value: answer.append(value))
        wait(lambda: bool(answer))
        return answer[0]
    with scratch() as temporary, crypt_fixture(temporary, executable.get_rclone_path()) as fixture:
        provider = fixture.provider
        browser_release = provider.acquire()
        DocumentResource.publish(provider, 'Notebook.rmdoc', Notebook.new('Qt private notebook').to_bytes(), max_bytes=MAX_ARCHIVE)
        resource = DocumentResource(provider, 'Notebook.rmdoc', max_bytes=MAX_ARCHIVE)
        resource.read()
        window = open_workspace(resource=resource)
        panel = window.centralWidget()
        panel.repository_root = temporary / 'ordinary-recovery'
        try:
            wait(lambda: evaluate(panel.web, 'typeof send === "function"'))
            assert panel.web.page().profile().isOffTheRecord()
            evaluate(panel.web, "send({op:'stroke',points:[[30,40,.4],[50,60,.8]],tool:12,width:3})")
            wait(lambda: panel.document.dirty and len(panel.editor.notebook.page(0).strokes) == 1)
            evaluate(panel.web, "send({op:'save'})")
            wait(lambda: not panel.busy and not panel.document.dirty)
            assert len(Notebook.read(resource.read()).page(0).strokes) == 1
            encrypted = provider.encrypted_path('Notebook.rmdoc')
            ciphertext = encrypted.read_bytes()
            assert b'Qt private notebook' not in ciphertext
            assert not panel.repository_root.exists()
            panel.web.grab().save(str(output / 'desktop-private.png'))
            local_root = temporary / 'local'
            local_root.mkdir()
            local = LocalFiles(local_root)
            choice = ResourceChoice(local, 'Copy.rmdoc')
            confirmed = []
            def confirm():
                dialog = app.activeModalWidget()
                if isinstance(dialog, qt.QMessageBox):
                    confirmed.append(dict(title=dialog.windowTitle(), text=dialog.text()))
                    dialog.button(qt.QMessageBox.StandardButton.Yes).click()
                else:
                    qt.QTimer.singleShot(20, confirm)
            # Exercise the actual desktop export action and native plaintext prompt.
            exported = local_root / 'Export.rmdoc'
            original_document = panel.document
            with patch.object(qt.QFileDialog, 'getSaveFileName', return_value=(str(exported), '')):
                qt.QTimer.singleShot(0, confirm)
                panel.perform(dict(op='export'))
                wait(lambda: not panel.busy)
            assert len(confirmed) == 1 and 'decrypted copy' in confirmed[0]['text']
            assert len(Notebook.read(exported.read_bytes()).page(0).strokes) == 1
            assert panel.document is original_document and panel.document.resource is resource
            assert len(Notebook.read(resource.read()).page(0).strokes) == 1
            assert encrypted.read_bytes() == ciphertext
            from commonUtils.filesystem.local_access import protect_local_root
            release_boundary = protect_local_root(object(), local_root, 'Use the document provider')
            blocked = local_root / 'Blocked.rmdoc'
            try:
                with patch.object(qt.QFileDialog, 'getSaveFileName', return_value=(str(blocked), '')):
                    qt.QTimer.singleShot(0, confirm)
                    panel.perform(dict(op='export'))
                wait(lambda: not panel.busy)
                assert not blocked.exists()
                assert panel.document is original_document and not panel.busy
            finally:
                release_boundary()
            # Appending .rmdoc must not bypass overwrite confirmation.
            with patch.object(qt.QFileDialog, 'getSaveFileName', return_value=(str(exported.with_suffix('')), '')), \
                    patch.object(qt.QMessageBox, 'question', side_effect=[qt.QMessageBox.StandardButton.Yes,
                                                                         qt.QMessageBox.StandardButton.Cancel]) as prompt:
                before_export = exported.read_bytes()
                panel.perform(dict(op='export'))
                assert prompt.call_count == 2
                assert exported.read_bytes() == before_export and panel.document is original_document
            confirmed.clear()
            with patch('services.documents.ui.editors.choose_editor_resource', return_value=choice):
                qt.QTimer.singleShot(0, confirm)
                assert panel.save_document(save_as=True)
            wait(lambda: not panel.busy)
            assert len(confirmed) == 1 and 'decrypted copy' in confirmed[0]['text']
            assert panel.document.resource.policy.persistent
            evaluate(panel.web, "send({op:'stroke',points:[[90,100,.4],[110,120,.8]],tool:12,width:3})")
            wait(lambda: panel.document.dirty)
            evaluate(panel.web, "send({op:'save'})")
            wait(lambda: not panel.busy and not panel.document.dirty)
            assert len(Notebook.read((local_root / 'Copy.rmdoc').read_bytes()).page(0).strokes) == 2
            assert encrypted.read_bytes() == ciphertext
            result = dict(success=True, cases=['qt-private-canvas-input', 'qt-encrypted-save',
                'qt-off-record-profile', 'qt-verified-export-copy', 'qt-protected-export-refused', 'qt-suffixed-export-overwrite-cancel', 'qt-native-decryption-confirmation', 'qt-save-as-retarget-and-resave'])
            (output / 'result.json').write_text(json.dumps(result, indent=2))
        finally:
            if panel.document:
                panel.document.dirty = False
            window.close()
            app.processEvents()
            browser_release()
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
