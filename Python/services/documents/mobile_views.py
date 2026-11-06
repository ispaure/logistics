"""Host policy for mobile document surfaces, retirement and source navigation."""


def retire_webview(view):
    from commonUtils.ui.native.text_size import native_backend
    from commonUtils.ui.native.inline_html import set_inline_html
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
        # Clear the live DOM immediately, even while this pane is hidden.
        # Keep the final navigation to replace the old document's script state.
        native.evaluateJavaScript('(()=>{const body=document.createElement("body");body.textContent="Document closed.";document.documentElement.replaceChildren(body);})()',
                                  completionHandler=None)
    set_inline_html(view, 'https://logistics.invalid/closed/', '<p>Document closed.</p>')


def document_webview(resource=None, *, inline_video=False, **options):
    """Choose the canvas privacy implementation at the host storage boundary."""
    import toga
    from toga.platform import get_factory
    private = resource is not None and not resource.policy.persistent
    backend = get_factory().WebView.__module__ if inline_video else ''
    view_type = toga.WebView
    if private:
        from commonUtils.ui.native.private_webview import PrivateWebView
        # Notebook archives allow 128 MiB expanded; an initial page can exceed
        # the text reader's HTML bound. The private adapter never stages HTML.
        view_type = PrivateWebView
        options['max_html_bytes'] = 128 * 1024 * 1024
    if inline_video and backend.startswith('toga_iOS.'):
        from rubicon.objc import CGRect, ObjCClass
        from toga_iOS.widgets.webview import TogaWebView, WebView

        class InlineBackend(WebView):
            def create(self):
                configuration = ObjCClass('WKWebViewConfiguration').alloc().init()
                configuration.allowsInlineMediaPlayback = True
                configuration.allowsPictureInPictureMediaPlayback = False
                configuration.allowsAirPlayForMediaPlayback = False
                # The Notes page starts media only after native audio approval.
                configuration.mediaTypesRequiringUserActionForPlayback = 0
                if private:
                    configuration.websiteDataStore = ObjCClass('WKWebsiteDataStore').nonPersistentDataStore()
                self.native = TogaWebView.alloc().initWithFrame(
                    CGRect((0, 0), (0, 0)), configuration=configuration)
                self.native.interface, self.native.impl = self.interface, self
                self.native.navigationDelegate = self.native
                self.native.UIDelegate = self.native
                self.loaded_future, self._allowed_url = None, None
                self.add_constraints()
                if private:
                    if self.native.configuration.websiteDataStore.isPersistent():
                        raise RuntimeError('Private view requires a nonpersistent WebView store.')
                    self.interface.private_configured = True

        class InlineVideoView(view_type):
            def _create(self):
                if private:
                    self.private_closed = self.private_configured = False
                return InlineBackend(interface=self)

        view_type = InlineVideoView
    view = view_type(**options)
    if inline_video and backend.startswith('toga_android.'):
        view._impl.settings.setMediaPlaybackRequiresUserGesture(False)
    return view


def markdown_webview(*, private=False, **options):
    """The host chooses a protected native surface; callers retain Source mode."""
    from mobile.keyboard import install_editor_accessory_policy
    install_editor_accessory_policy()
    from types import SimpleNamespace
    from services.documents.storage import DocumentPolicy
    if private:
        from commonUtils.ui.native.private_webview import private_webview_supported
        if not private_webview_supported():
            raise ValueError('Private formatted Markdown is unavailable here. Use Source mode.')
    return document_webview(SimpleNamespace(policy=DocumentPolicy(not private, True)), **options)


async def show_reader_source(app, provider, path):
    """Admit a reader's source and reveal it through the host's file browser."""
    from services.documents.mobile_reading import reading_capabilities
    from services.documents.mobile_storage import document_source
    from mobile.document_sources import show_folder_location
    copies, key = document_source(provider, path)
    location = (dict(remote=copies.remote, key=key) if reading_capabilities(copies).remote
                else dict(provider=provider, key=path))
    return await show_folder_location(app, location)
