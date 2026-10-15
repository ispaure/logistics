"""Feature-owned private EPUB WebViews; content stays in RAM, never Toga's file cache.

Toolkit adapters are selected by the active backend, not the host OS. Unsupported
backends use the native text fallback rather than an ordinary persistent WebView.
"""
import toga
from toga.platform import get_factory

MAX_HTML = 2 * 1024 * 1024


def private_webview_supported():
    return get_factory().WebView.__module__.startswith(('toga_iOS.', 'toga_android.'))


class PrivateWebView(toga.WebView):
    def _create(self):
        backend = self.factory.WebView.__module__
        self.private_closed = False
        self.private_configured = False
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, CGRect
            from toga_iOS.widgets.webview import WebView, TogaWebView
            class PrivateBackend(WebView):
                def create(inner):
                    configuration = ObjCClass('WKWebViewConfiguration').alloc().init()
                    store = ObjCClass('WKWebsiteDataStore').nonPersistentDataStore()
                    configuration.websiteDataStore = store
                    inner.native = TogaWebView.alloc().initWithFrame(
                        CGRect((0, 0), (0, 0)), configuration=configuration)
                    inner.native.interface, inner.native.impl = inner.interface, inner
                    inner.native.navigationDelegate = inner.native
                    inner.native.UIDelegate = inner.native
                    try:
                        inner.native.inspectable = False
                    except AttributeError:
                        pass
                    inner.loaded_future, inner._allowed_url = None, None
                    inner.add_constraints()
                    if bool(store.isPersistent()):
                        raise RuntimeError('Private book requires a nonpersistent WebView store.')
                    inner.interface.private_configured = True
            return PrivateBackend(interface=self)
        if backend.startswith('toga_android.'):
            from toga_android.widgets.webview import WebView
            from android.webkit import WebView as NativeWebView, WebSettings
            class PrivateBackend(WebView):
                def create(inner):
                    super().create()
                    inner.settings.setDomStorageEnabled(False)
                    inner.settings.setDatabaseEnabled(False)
                    inner.settings.setSaveFormData(False)
                    inner.settings.setCacheMode(WebSettings.LOAD_NO_CACHE)
                    inner.settings.setAllowFileAccess(False)
                    inner.settings.setAllowContentAccess(False)
                    NativeWebView.setWebContentsDebuggingEnabled(False)
                    inner.interface.private_configured = True
            return PrivateBackend(interface=self)
        raise RuntimeError('This backend does not support a private rich book view.')

    def set_content(self, root_url, content):
        if self.private_closed or not self.private_configured:
            raise RuntimeError('Private book view is closed or unprotected.')
        # Toga Android writes larger HTML documents to its disk cache. Keep the
        # byte bound as well as the character bound, before entering the toolkit.
        if len(content.encode('utf-8')) > MAX_HTML:
            raise ValueError('Private EPUB HTML exceeds the 2 MiB memory-only limit.')
        return super().set_content(root_url, content)

    def clear_private_content(self):
        if self.private_closed:
            return
        self.private_closed = True
        self.on_webview_load = None
        self.on_navigation_starting = lambda widget, url, **kw: False
        native = self._impl.native
        native.stopLoading()
        if self.factory.WebView.__module__.startswith('toga_iOS.'):
            native.loadHTMLString('', baseURL=None)
            native.navigationDelegate = None
            native.UIDelegate = None
        else:
            native.loadData('', 'text/html', 'utf-8')
            native.clearHistory()
            native.removeAllViews()
            native.destroy()
