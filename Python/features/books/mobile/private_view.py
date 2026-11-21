"""Books' memory-only HTML policy over the reusable native WebView."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.ui.native.private_webview import PrivateWebView as _PrivateWebView, private_webview_supported

MAX_HTML = 2 * 1024 * 1024


class PrivateWebView(_PrivateWebView):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_html_bytes', MAX_HTML)
        super().__init__(*args, **kwargs)
