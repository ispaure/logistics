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
