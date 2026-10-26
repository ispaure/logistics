"""Run native Qt deletion/Recent acceptance with disposable documents and evidence."""
import argparse
import json
import os
from pathlib import Path
import time
import traceback

from Scripts.build_retention import scratch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = dict(success=False, cases=[])
    with scratch() as workspace:
        os.environ['COMMONUTILS_STORAGE_ROOT'] = str(workspace / 'common')
        from commonUtils.ui import pyside as qt
        from features.text_editor.ui.service import EditorService
        # Keep QMessageBox widgets inspectable on Cocoa; native NSAlert helpers
        # do not expose their buttons through Qt's widget inventory.
        qt.QApplication.setAttribute(qt.Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
        app = qt.QApplication.instance() or qt.QApplication([])
        app.setQuitOnLastWindowClosed(False)
        report['platform'] = app.platformName()
        service = EditorService(app, history_path=workspace / 'recent.json',
                                preferences_path=workspace / 'preferences.ini')

        def wait(predicate, timeout=10):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                app.processEvents()
                if predicate():
                    return
                time.sleep(.02)
            raise TimeoutError('Native desktop document state did not arrive')

        def capture(window, name):
            app.processEvents()
            assert window.grab().save(str(output / (name + '.png')))

        dialogs = []
        answer = qt.QMessageBox.StandardButton.Ok
        def dismiss():
            for widget in app.topLevelWidgets():
                if isinstance(widget, qt.QMessageBox) and widget.isVisible():
                    button = widget.button(answer)
                    if button is not None:
                        dialogs.append(widget.text())
                        capture(widget, 'desktop-dialog-' + str(len(dialogs)))
                        button.click()
        timer = qt.QTimer()
        timer.timeout.connect(dismiss)
        timer.start(100)
        try:
            for suffix in ('.txt', '.md'):
                for dirty in (False, True):
                    name = ('dirty' if dirty else 'clean') + suffix
                    path = workspace / name
                    path.write_text('# Original desktop content\n')
                    window = service.open(path)
                    wait(lambda: not window.task.busy and window.current is not None)
                    document = window.current
                    if dirty:
                        document.editor.insertPlainText('Retained unsaved edit\n')
                        assert document.modified, 'Fixture did not become modified'
                    expected = document.editor.toPlainText()
                    window._recent_menu()
                    assert any(action.toolTip() == str(path) for action in window.recent_menu.actions())
                    path.unlink()
                    wait(lambda: document.external_changed)
                    assert document.editor.toPlainText() == expected
                    assert window.external_bar.isVisible()
                    window._recent_menu()
                    assert not any(action.toolTip() == str(path) for action in window.recent_menu.actions())
                    capture(window, name + '-deleted-open')
                    if dirty:
                        before = len(dialogs)
                        answer = qt.QMessageBox.StandardButton.Ok
                        assert window.save_document(), 'Save did not start'
                        wait(lambda: not window.task.busy and len(dialogs) > before)
                        assert 'deleted' in dialogs[-1].lower(), dialogs[-1]
                        assert document.modified, 'Failed save cleared modified state'
                        assert document.editor.toPlainText() == expected, (expected, document.editor.toPlainText())
                    assert not path.exists()
                    answer = qt.QMessageBox.StandardButton.Discard
                    assert window.close_tab(0)
                    wait(lambda: window.current is None)
                    window._recent_menu()
                    assert not any(action.toolTip() == str(path) for action in window.recent_menu.actions())
                    assert not path.exists()
                    capture(window, name + '-closed-recent')
                    report['cases'].append(dict(format=suffix, dirty=dirty,
                        file_watcher_notified=True, live_buffer_retained=True,
                        save_rejected=dirty, absent_while_open=True, absent_after_close=True))
                    window.close()
                    app.processEvents()
            report['dialogs'] = dialogs
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
            report['diagnostics'] = dict(busy=window.task.busy, result=str(window.task._result),
                modified=document.modified, text=document.editor.toPlainText(), expected=expected,
                dialogs=dialogs, windows=[(type(widget).__name__, widget.isVisible())
                                         for widget in app.topLevelWidgets()])
        finally:
            timer.stop()
            for window in tuple(service.windows):
                for document in window.documents:
                    document.editor.document().setModified(False)
                window.close()
            service.session.timer.stop()
            app.processEvents()
            (output / 'desktop-result.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
