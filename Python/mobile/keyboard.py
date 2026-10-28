"""Logistics keyboard-viewport policy over shared native dismissal."""
from commonUtils.ui.native.keyboard import install as install_dismissal


def prepare_picker_input(control):
    """Keep filename/folder completion in the app during landscape typing."""
    if type(control._impl).__module__.startswith('toga_android.'):
        from android.view.inputmethod import EditorInfo
        native = control._impl.native
        native.setImeOptions(native.getImeOptions() | EditorInfo.IME_FLAG_NO_EXTRACT_UI
                             | EditorInfo.IME_FLAG_NO_FULLSCREEN)



def reveal_picker_input(picker):
    """Keep the current UIKit first responder inside the resized picker viewport."""
    scroll = picker.picker_form._impl.native
    focused = next((control._impl.native for control in (picker.save_as_name, picker.new_folder_name)
                    if control._impl.native.isFirstResponder
                    and control._impl.native.isDescendantOfView(scroll)), None)
    if focused is None:
        return
    picker.app.main_window._impl.native.layoutIfNeeded()
    # Toga refreshes scroll content on a deferred native callback. Refresh now
    # before scrolling, so its content size cannot clamp away the needed offset.
    picker.save_as_view.refresh()
    scroll.layoutIfNeeded()
    scroll.scrollRectToVisible(focused.convertRect(focused.bounds, toView=scroll), animated=False)


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
