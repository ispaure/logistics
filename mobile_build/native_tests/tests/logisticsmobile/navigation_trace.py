"""Bounded native-fixture policy evidence; delegate decisions stay unchanged."""
import inspect


def native_event(native, phase, error=None):
    """Passive WebKit callbacks; all toolkit decision/load handlers are inherited."""
    try:
        import json
        from commonUtils.ui.native.keyboard import native_value
        view = native.interface
        if view is None:
            return
        event = dict(phase=phase, url=str(native_value(native.URL))[:180],
            loading=bool(native.isLoading()), progress=float(native_value(native.estimatedProgress)),
            allowed_url=getattr(view._impl, '_allowed_url', None),
            error=None if error is None else str(error)[:800])
        trace = view.__dict__.setdefault('_native_load_trace', [])
        trace.append(event)
        del trace[:-32]
        print('LOGISTICS_NATIVE_LOAD_EVENT=' + json.dumps(event), flush=True)
    except Exception as failure:
        print('LOGISTICS_NATIVE_LOAD_DIAGNOSTIC_ERROR=' + str(failure), flush=True)


def install_ios_events():
    from toga.platform import get_factory
    if not get_factory().WebView.__module__.startswith('toga_iOS.'):
        return
    from rubicon.objc import objc_method, py_from_ns
    from toga_iOS.widgets import webview
    original = webview.TogaWebView
    class LogisticsLoadDiagnosticWebView(original):
        @objc_method
        def webView_didStartProvisionalNavigation_(self, webview, navigation) -> None:
            native_event(self, 'start')
        @objc_method
        def webView_didCommitNavigation_(self, webview, navigation) -> None:
            native_event(self, 'commit')
        @objc_method
        def webView_didFailProvisionalNavigation_withError_(self, webview, navigation, error) -> None:
            native_event(self, 'provisional-error', py_from_ns(error))
        @objc_method
        def webView_didFailNavigation_withError_(self, webview, navigation, error) -> None:
            native_event(self, 'load-error', py_from_ns(error))
        @objc_method
        def webViewWebContentProcessDidTerminate_(self, webview) -> None:
            native_event(self, 'web-process-terminated')
    webview.TogaWebView = LogisticsLoadDiagnosticWebView


def install():
    import toga
    original = toga.WebView.__init__
    if getattr(original, '_native_policy_trace', False):
        return
    install_ios_events()

    def create(view, *args, **kwargs):
        callback = kwargs.get('on_navigation_starting')
        view._native_policy_trace = trace = []
        if callback is not None and not inspect.iscoroutinefunction(callback):
            def decision(widget, url, **options):
                allowed = callback(widget, url=url, **options)
                trace.append(dict(url=str(url).split('?', 1)[0][:180],
                                  allowed=allowed if isinstance(allowed, bool) else None))
                del trace[:-32]
                return allowed
            kwargs['on_navigation_starting'] = decision
        original(view, *args, **kwargs)

    create._native_policy_trace = True
    toga.WebView.__init__ = create
