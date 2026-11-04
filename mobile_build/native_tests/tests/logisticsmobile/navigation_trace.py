"""Bounded native-fixture policy evidence; delegate decisions stay unchanged."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import inspect
import json
from pathlib import Path
from weakref import WeakValueDictionary

_lifecycle = None


class WebViewLifecycle:
    """Count views without retaining them or changing their disposal lifetime."""
    def __init__(self, cache=None):
        self.cache = None if cache is None else Path(cache)
        self.created = 0
        self.starts = 0
        self.views = WeakValueDictionary()
        self.native_views = None

    def create(self, view):
        self.created += 1
        self.views[self.created] = view
        self.save()
        return self.created

    def snapshot(self):
        views = list(self.views.values())
        result = dict(views_created=self.created, navigations_started=self.starts,
                    live_python_views=len(views),
                    live_retired_views=sum(bool(getattr(view, 'private_closed', False)) for view in views))
        if self.native_views is not None:
            result['live_native_views'] = int(self.native_views.count)
        return result

    def save(self):
        if self.cache is not None:
            try:
                self.cache.mkdir(parents=True, exist_ok=True)
                (self.cache / 'logistics-native-ui-webview-counts.json').write_text(
                    json.dumps(self.snapshot()) + '\n')
            except OSError:
                pass  # Counting cannot change native test acceptance.


def lifecycle_snapshot():
    return None if _lifecycle is None else _lifecycle.snapshot()


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
        if _lifecycle is not None:
            _lifecycle.starts += phase == 'start'
            _lifecycle.save()
            event.update(view_index=getattr(view, '_native_view_index', None),
                         lifecycle=_lifecycle.snapshot())
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
    from rubicon.objc import ObjCClass, objc_method, py_from_ns
    # This single test-lifetime table holds weak native references. Counting
    # Python wrappers alone cannot establish WKWebView release.
    _lifecycle.native_views = ObjCClass('NSHashTable').weakObjectsHashTable().retain()
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


def install(cache=None):
    global _lifecycle
    import toga
    original = toga.WebView.__init__
    if getattr(original, '_native_policy_trace', False):
        return
    _lifecycle = WebViewLifecycle(cache)
    install_ios_events()

    def create(view, *args, **kwargs):
        view._native_view_index = _lifecycle.create(view)
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
        if _lifecycle.native_views is not None:
            _lifecycle.native_views.addObject(view._impl.native)
            _lifecycle.save()

    create._native_policy_trace = True
    toga.WebView.__init__ = create
