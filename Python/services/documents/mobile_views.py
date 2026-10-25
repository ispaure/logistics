"""Logistics document privacy policy for retiring mobile web content."""


def retire_webview(view):
    from commonUtils.ui.native.text_size import native_backend
    binding = getattr(view, '_font_binding', None)
    if binding is not None:
        binding.dispose()
    clear_private = getattr(view, 'clear_private_content', None)
    if clear_private is not None:
        parent = getattr(view, 'parent', None)
        if parent is not None:
            parent.remove(view)
        clear_private()
        return
    native = getattr(view._impl, 'native', None)
    if native_backend(view).startswith('toga_iOS.') and native is not None:
        native.stopLoading()
        native.navigationDelegate = None
        native.UIDelegate = None
        # WKWebView can defer replacement navigation while its pane is hidden.
        # Clear the live document before queuing that navigation, so retired
        # text cannot remain in an offscreen editor or Notes Library preview.
        native.evaluateJavaScript('document.open();document.write("<p>Document closed.</p>");document.close();',
                                  completionHandler=None)
    view.set_content('https://logistics.invalid/closed/', '<p>Document closed.</p>')


def document_webview(resource=None, **options):
    """Choose the canvas privacy implementation at the host storage boundary."""
    if resource is not None and not resource.policy.persistent:
        from commonUtils.ui.native.private_webview import PrivateWebView
        # Notebook archives allow 128 MiB expanded; an initial page can exceed
        # the text reader's HTML bound. The private adapter never stages HTML.
        return PrivateWebView(max_html_bytes=128 * 1024 * 1024, **options)
    import toga
    return toga.WebView(**options)


def markdown_webview(*, private=False, **options):
    """The host chooses a protected native surface; callers retain Source mode."""
    from types import SimpleNamespace
    from services.documents.storage import DocumentPolicy
    if private:
        from commonUtils.ui.native.private_webview import private_webview_supported
        if not private_webview_supported():
            raise ValueError('Private formatted Markdown is unavailable here. Use Source mode.')
    return document_webview(SimpleNamespace(policy=DocumentPolicy(not private, True)), **options)
