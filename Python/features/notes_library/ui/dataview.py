"""Disposable Chromium execution with native Notes Library reading output."""
import json

from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown.viewer import MarkdownViewer
from commonUtils.ui.tasks.operation_progress import OperationProgress
from ..dataview import ViewFiles, view_plan, runtime_script, javascript, completed_results
from ..dataview_script import POLL, worker_policy


class NotesMarkdownViewer(MarkdownViewer):
    def __init__(self, *args, **kwargs):
        self.data_views = None
        self.view_key = self.view_output = None
        super().__init__(*args, **kwargs)

    def clear_data_views(self):
        self.view_key = self.view_output = None
        if self.data_views is not None:
            self.data_views.stop()

    def set_editing(self, enabled):
        super().set_editing(enabled)
        if self.edit_button.isChecked():
            self.clear_data_views()

    def _render_source(self, text, **kwargs):
        owner = self.storage.window
        if (owner.locked or owner.closing or self.storage.path is None or owner.library is None
                or self.edit_button.isChecked()):
            self.clear_data_views()
            return super()._render_source(text, **kwargs)
        key = (self.storage.path, text)
        if key != self.view_key:
            self.clear_data_views()
            self.view_key = key
            try:
                plan = view_plan(text)
                if plan.scripts:
                    if self.data_views is None:
                        self.data_views = DesktopViews(self)
                        self.data_views.progress.completed.connect(lambda *_: owner.close() if owner.closing or owner.locked else None)
                    self.view_output = plan.render()
                    relative = self.storage.path.relative_to(owner.provider.root.resolve()).as_posix()
                    self.data_views.start(plan, ViewFiles(owner.library, relative), key)
            except ValueError as error:
                self.view_output = 'Data view error: ' + str(error) + '\n\n' + text
        return super()._render_source(self.view_output if self.view_output is not None else text, **kwargs)


class DesktopViews(qt.QObject):
    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.page = None
        self.pending = None
        self.generation = 0
        self.polling = False
        self.progress = OperationProgress(viewer)
        viewer.storage.window.operation_footer.layout().addWidget(self.progress, 1)
        self.progress.hide()
        self.progress.completed.connect(self.read_completed)
        self.timer = qt.QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.poll)
        self.deadline = qt.QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.setInterval(35000)
        self.deadline.timeout.connect(lambda: self.finish(
            ['Data view error: execution exceeded 35 seconds.'] * len(self.plan.scripts)))

    def stop(self):
        self.generation += 1
        self.pending = None
        self.progress.request_cancel()
        self.timer.stop()
        self.deadline.stop()
        self.polling = False
        if self.page is not None:
            self.page.triggerAction(self.page.WebAction.Stop)
            self.page.deleteLater()
            self.page = None
        self.files = self.plan = None

    def start(self, plan, files, key):
        self.pending = (plan, files, key)
        if not self.progress.busy:
            self.launch()

    def launch(self):
        if self.pending is None:
            return
        # Load WebEngine lazily: ordinary Markdown does not need Chromium.
        from PySide6 import QtQuick, QtQuickWidgets
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        _bindings = (QtQuick, QtQuickWidgets)

        class Page(QWebEnginePage):
            def acceptNavigationRequest(self, url, kind, main):
                return url.scheme() in ('about', 'data')

        self.plan, self.files, self.key = self.pending
        self.pending = None
        # The profile must outlive its page, including deferred native teardown.
        # Parenting it to the page can retire Chromium resources too early.
        profile = QWebEngineProfile(qt.QApplication.instance())
        self.page = Page(profile, self)
        self.page.destroyed.connect(profile.deleteLater)
        generation = self.generation
        def loaded(ok):
            if generation != self.generation or self.page is None:
                return
            if not ok:
                self.finish(['Data view error: JavaScript runtime could not load.'] * len(self.plan.scripts))
                return
            self.page.runJavaScript(runtime_script(self.plan))
            self.timer.start()
        self.page.loadFinished.connect(loaded)
        self.deadline.start()
        self.page.setHtml(worker_policy('<!doctype html><meta http-equiv="Content-Security-Policy" content="default-src \'none\';"><body></body>'))

    def poll(self):
        if self.page is None or self.polling or self.progress.busy:
            return
        self.polling = True
        generation = self.generation
        def received(raw):
            if generation != self.generation or self.page is None:
                return
            self.polling = False
            if not raw:
                return
            try:
                state = json.loads(raw)
                if state['done']:
                    self.finish(completed_results(state, len(self.plan.scripts)))
                elif state['requests']:
                    messages, files = state['requests'], self.files
                    def read(report, cancelled):
                        return generation, [files.request(message, cancelled=cancelled) for message in messages]
                    self.progress.start(read, message='Reading data view files…')
            except (ValueError, TypeError, KeyError) as error:
                self.finish(['Data view error: ' + str(error)] * len(self.plan.scripts))
        self.page.runJavaScript(POLL, received)

    def read_completed(self, result, error):
        self.progress.hide()
        if result is not None and result[0] == self.generation and self.page is not None:
            for reply in result[1]:
                self.page.runJavaScript('window.logisticsDataView?.reply(' + javascript(reply) + ')')
        elif error and self.page is not None and not self.progress.cancelled.is_set():
            self.finish(['Data view error: ' + error] * len(self.plan.scripts))
        if self.pending is not None:
            self.launch()

    def finish(self, results):
        viewer, key = self.viewer, self.key
        rendered = self.plan.render(results)
        self.stop()
        if viewer.view_key == key:
            viewer.view_output = rendered
            viewer._render_source(viewer.markdown_text())
