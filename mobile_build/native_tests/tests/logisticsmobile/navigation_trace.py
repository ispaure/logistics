"""Bounded native-fixture policy evidence; delegate decisions stay unchanged."""
import inspect


def install():
    import toga
    original = toga.WebView.__init__
    if getattr(original, '_native_policy_trace', False):
        return

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
