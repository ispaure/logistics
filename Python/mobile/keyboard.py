"""Logistics keyboard-viewport policy over shared native dismissal."""
from commonUtils.ui.native.keyboard import install as install_dismissal

_editor_accessory_installed = False


def install_editor_accessory_policy():
    """Keep WebKit's form navigation accessory out of document editors."""
    global _editor_accessory_installed
    from toga.platform import get_factory
    if _editor_accessory_installed or not get_factory().WebView.__module__.startswith('toga_iOS.'):
        return
    from rubicon.objc import ObjCInstance, objc_id, objc_method, send_super
    import toga_iOS.widgets.webview as webviews

    class LogisticsEditorWebView(webviews.TogaWebView):
        @objc_method
        def inputAccessoryView(self) -> objc_id:
            if getattr(self.interface, '_document_editor', False):
                return None
            result = send_super(__class__, self, 'inputAccessoryView', restype=objc_id)
            return ObjCInstance(result) if result else None

    # Both ordinary and memory-only WebViews construct through this symbol.
    # Only explicitly marked editing surfaces suppress the system accessory.
    webviews.TogaWebView = LogisticsEditorWebView
    _editor_accessory_installed = True


def prepare_picker_input(control):
    """Keep filename/folder completion in the app during landscape typing."""
    if type(control._impl).__module__.startswith('toga_android.'):
        from android.view.inputmethod import EditorInfo
        native = control._impl.native
        native.setImeOptions(native.getImeOptions() | EditorInfo.IME_FLAG_NO_EXTRACT_UI
                             | EditorInfo.IME_FLAG_NO_FULLSCREEN)



def dismiss_picker_keyboard(picker, field=None):
    field = picker.save_as_name if field is None else field
    backend = type(field._impl).__module__
    if backend.startswith('toga_android.'):
        from android.content import Context
        native = field._impl.native
        native.getContext().getSystemService(Context.INPUT_METHOD_SERVICE).hideSoftInputFromWindow(
            native.getWindowToken(), 0)
        native.clearFocus()
    elif backend.startswith('toga_iOS.'):
        picker.app.main_window._impl.native.endEditing(True)


def reset_picker_keyboard(picker, *, keep=None):
    """Remove only the extra scroll inset owned by the picker keyboard reveal."""
    for name in ('name_form', 'picker_form'):
        form = getattr(picker, name, None)
        if form is None or form is keep or not hasattr(form, '_keyboard_bottom_inset'):
            continue
        scroll = form._impl.native
        insets = scroll.contentInset
        if abs(float(insets.bottom) - form._keyboard_bottom_inset) > .5:
            insets.bottom = form._keyboard_bottom_inset
            scroll.contentInset = insets
        del form._keyboard_bottom_inset


def reveal_picker_input(picker):
    """Keep the current UIKit first responder inside the resized picker viewport."""
    editing_name = picker.name_panel is not None and picker.save_as_name._impl.native.isFirstResponder
    form = picker.name_form if editing_name else picker.picker_form
    scroll = form._impl.native
    focused = next((control._impl.native for control in (picker.save_as_name, picker.new_folder_name)
                    if control._impl.native.isFirstResponder
                    and control._impl.native.isDescendantOfView(scroll)), None)
    if focused is None:
        reset_picker_keyboard(picker)
        return
    window = picker.app.main_window._impl.native
    window.layoutIfNeeded()
    # Toga refreshes scroll content on a deferred native callback. Refresh now
    # before scrolling, so its content size cannot clamp away the needed offset.
    form.content.refresh()
    scroll.layoutIfNeeded()
    scroll.scrollRectToVisible(focused.convertRect(focused.bounds, toView=scroll), animated=False)
    adapter = picker.app.native_host.adapter
    if not adapter.keyboard_visible or adapter.keyboard_frame is None:
        reset_picker_keyboard(picker)
        return
    reset_picker_keyboard(picker, keep=form)
    keyboard = window.convertRect(adapter.keyboard_frame, fromCoordinateSpace=window.screen.coordinateSpace)
    viewport = scroll.convertRect(scroll.bounds, toView=window)
    insets = scroll.contentInset
    if not hasattr(form, '_keyboard_bottom_inset'):
        form._keyboard_bottom_inset = float(insets.bottom)
    automatic = max(0, float(scroll.adjustedContentInset.bottom) - float(insets.bottom))
    covered = max(0, min(float(viewport.size.height),
        float(viewport.origin.y + viewport.size.height - keyboard.origin.y)))
    bottom_inset = form._keyboard_bottom_inset + max(0, covered - automatic)
    if abs(float(insets.bottom) - bottom_inset) > .5:
        insets.bottom = bottom_inset
        scroll.contentInset = insets
    scroll.layoutIfNeeded()
    # A retained UIKit scroll view can still span the keyboard after rotation.
    # Its ordinary visibility check then succeeds for a physically covered
    # field. Use the actual window keyboard edge and permit the needed offset.
    rect = focused.convertRect(focused.bounds, toView=window)
    adjusted = scroll.adjustedContentInset
    top = float(viewport.origin.y + adjusted.top)
    bottom = min(float(viewport.origin.y + viewport.size.height - adjusted.bottom),
                 float(keyboard.origin.y))
    offset = scroll.contentOffset
    previous = float(offset.y)
    if rect.origin.y + rect.size.height > bottom:
        offset.y += rect.origin.y + rect.size.height - bottom
    elif rect.origin.y < top:
        offset.y += rect.origin.y - top
    minimum = -float(adjusted.top)
    maximum = max(minimum, float(scroll.contentSize.height - scroll.bounds.size.height + adjusted.bottom))
    offset.y = max(minimum, min(maximum, float(offset.y)))
    if abs(float(offset.y) - previous) > .5:
        scroll.setContentOffset(offset, animated=False)


def picker_keyboard_visible(app, adapter):
    visible = bool(getattr(adapter, 'keyboard_visible', False)
                   or getattr(adapter, 'keyboard_chrome', None) is not None)
    native = getattr(getattr(adapter, 'impl', None), 'native', None)
    if (type(getattr(app, '_impl', None)).__module__.startswith('toga_android.')
            and native is not None and hasattr(native, 'getRootWindowInsets')):
        from java import jclass
        insets = jclass('androidx.core.view.ViewCompat').getRootWindowInsets(native)
        if insets is not None:
            return bool(insets.isVisible(jclass('androidx.core.view.WindowInsetsCompat$Type').ime()))
    return visible


def _tuck_control(control, compact):
    mounted = getattr(control, '_keyboard_mount', None)
    if compact and mounted is None and control.parent is not None:
        parent = control.parent
        index = parent.children.index(control)
        following = parent.children[index + 1] if index + 1 < len(parent.children) else None
        control._keyboard_mount = parent, following, index
        # Pack.display does not remove native Android child views. Reparent
        # the same control so it frees space without leaving a touch overlay.
        parent.remove(control)
    elif not compact and mounted is not None:
        parent, following, index = mounted
        control._keyboard_mount = None
        if control.parent is None:
            index = parent.children.index(following) if following in parent.children else min(index, len(parent.children))
            parent.insert(index, control)


def _fit_toolbar(toolbar, compact):
    heights = getattr(toolbar, '_keyboard_heights', {})
    if compact:
        for control in toolbar.children:
            if control.style.height is not None and control.style.height > 44:
                heights.setdefault(control, control.style.height)
                control.style.height = 44
        toolbar._keyboard_heights = heights
    elif heights:
        toolbar._keyboard_heights = {}
        for control, height in heights.items():
            control.style.height = height


def _fit_source(editor, compact):
    native = getattr(editor._impl, 'native', None)
    if native is None or not hasattr(native, 'getPaddingTop'):
        return
    saved = getattr(editor, '_keyboard_padding', None)
    if compact:
        if saved is None:
            editor._keyboard_padding = native.getPaddingTop(), native.getPaddingBottom(), editor.style.margin_top
        if native.getPaddingTop() or native.getPaddingBottom():
            native.setPadding(native.getPaddingLeft(), 0, native.getPaddingRight(), 0)
        if editor.style.margin_top:
            editor.style.margin_top = 0
    elif saved is not None:
        editor._keyboard_padding = None
        top, bottom, margin = saved
        native.setPadding(native.getPaddingLeft(), top, native.getPaddingRight(), bottom)
        editor.style.margin_top = margin


def fit_editors(app):
    """Reserve the short Android IME viewport for text and its main toolbar."""
    adapter = getattr(getattr(app, 'native_host', None), 'adapter', None)
    if adapter is None:
        return
    picker = getattr(app, '_editor_picker', None)
    if picker is not None:
        picker.fit_keyboard(picker_keyboard_visible(app, adapter))
    if not hasattr(adapter, 'keyboard_chrome'):
        return
    compact = adapter.keyboard_chrome is not None
    for owner in tuple(getattr(app, 'text_views', {}).values()):
        _fit_toolbar(owner.toolbar, compact)
        _fit_source(owner.editor, compact)
        for control in (owner.source_tools, owner.status):
            _tuck_control(control, compact)
        margin = 0 if compact else 12
        if owner.document_view.style.margin_top != margin:
            owner.document_view.style.margin = margin
    manager = getattr(app, 'private_sessions', None)
    for owner in tuple(getattr(manager, 'controllers', {}).values()):
        footer = getattr(owner, 'crypt_markdown_footer', None)
        if footer is not None:
            _fit_toolbar(owner.reader_toolbar, compact)
            _fit_source(owner.crypt_text, compact)
            _tuck_control(footer, compact)



def install(app):
    previous = getattr(app, '_keyboard_dismissal', None)
    if previous is not None:
        previous.dispose()
    app._keyboard_dismissal = install_dismissal(app.main_window)
