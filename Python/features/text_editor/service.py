"""One shared editor window per QApplication; browser windows never own buffers."""
from commonUtils.ui import pyside as qt


class EditorService(qt.QObject):
    idle=qt.Signal()
    saved=qt.Signal(object)
    def __init__(self,parent):
        super().__init__(parent);self.window=None
    def open(self,path=None,*,force=False):
        from .window import EditorWindow
        if self.window is None:
            self.window=EditorWindow();self.window.idle.connect(self.idle);self.window.saved.connect(self.saved)
        if not self.window.tabs.count():self.window.new_document()
        if path is not None:self.window.open_path(path,force=force)
        self.window.show();self.window.raise_();self.window.activateWindow()
        return self.window
    def prepare_close(self):
        if self.window is None:return True
        if not self.window.prepare_close():return False
        self.window.close();return True


def editor_service():
    app=qt.QApplication.instance()
    if not hasattr(app,'_logistics_text_editor'):app._logistics_text_editor=EditorService(app)
    return app._logistics_text_editor


class BrowserController(qt.QObject):
    idle=qt.Signal()
    def __init__(self,host):
        super().__init__(host);self.service=editor_service()
        browser=getattr(host,'file_browser',host)
        refresh=getattr(browser,'refresh_item',None)
        if refresh:self.service.saved.connect(refresh)
    def open(self,path,*,force=False):return self.service.open(path,force=force)
    def prepare_close(self):return True
