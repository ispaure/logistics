"""Books' memory-only HTML policy over the reusable native WebView."""
from commonUtils.ui.native.private_webview import PrivateWebView as _PrivateWebView, private_webview_supported

MAX_HTML = 2 * 1024 * 1024


class PrivateWebView(_PrivateWebView):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_html_bytes', MAX_HTML)
        super().__init__(*args, **kwargs)
