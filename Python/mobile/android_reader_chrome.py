"""Mount existing document controls in Android's single native action bar."""
from .palette import android_palette


def release_buttons(adapter):
    saved = getattr(adapter, '_reader_action_bar_insets', None)
    if saved is not None:
        toolbar, start, end = saved
        toolbar.setContentInsetsRelative(start, end)
        adapter._reader_action_bar_insets = None
    adapter._reader_action_bar_fit = None
    for button in getattr(adapter, '_reader_action_bar_buttons', ()):
        native = button._impl.native
        parent = native.getParent()
        if parent is not None:
            parent.removeView(native)
    adapter._reader_action_bar_buttons = ()


def set_bar_visibility(adapter, bar, visible):
    """Keep the short-viewport keyboard override and its restore state in sync."""
    keyboard = getattr(adapter, 'keyboard_chrome', None)
    if keyboard is not None:
        navigation, visibility, title, showing = keyboard
        if title == bar:
            adapter.keyboard_chrome = (navigation, visibility, title, visible)
            if visible and getattr(adapter, '_reader_action_bar_keep_keyboard', False):
                bar.show()
            else:
                bar.hide()
            return
    bar.show() if visible else bar.hide()


def fit_document_title(root, label, leading_count, trailing_count, *, notes_controls=()):
    """Keep a hold target even when Notes Library has more actions than fit."""
    from android.view import View
    from android.widget import HorizontalScrollView
    from java import dynamic_proxy

    density = root.getResources().getDisplayMetrics().density
    title_index = root.indexOfChild(label.getParent())
    actions = root.getChildAt(root.getChildCount() - 1)
    params = actions.getLayoutParams()
    root.removeView(actions)
    scroll = HorizontalScrollView(root.getContext())
    scroll.addView(actions, -2, -1)
    root.addView(scroll, params)

    def fit(width):
        if width <= 0:
            return
        from commonUtils.ui.native.bars import android_title_insets
        unit = round((notes_controls[0].style.width if notes_controls else 48) * density)
        for button in notes_controls:
            native = button._impl.native
            params = native.getLayoutParams()
            if params.width != unit:
                params.width = unit
                native.setLayoutParams(params)
                padding = round((2 if button.style.width < 48 else 12) * density)
                native.setPaddingRelative(padding, native.getPaddingTop(), padding, native.getPaddingBottom())
            close = getattr(button._impl, '_android_surface_size', None) is not None
            if close or button is notes_controls[-1]:
                icon_width = button._impl._control_drawable.getBounds().width()
                space = max(0, unit - icon_width)
                start_padding = space // 2 if close else min(space, round(
                    (6 if button.style.width < 48 else 16) * density))
                end_padding = space - start_padding
                if (native.getPaddingStart(), native.getPaddingEnd()) != (start_padding, end_padding):
                    native.setPaddingRelative(start_padding, native.getPaddingTop(),
                                              end_padding, native.getPaddingBottom())
        start, end = android_title_insets(width, leading_count, trailing_count, size=unit)
        titles = root.getChildAt(title_index)
        margins = titles.getLayoutParams()
        if margins.getMarginStart() != start or margins.getMarginEnd() != end:
            margins.setMarginStart(start)
            margins.setMarginEnd(end)
            titles.setLayoutParams(margins)
        bounds = scroll.getLayoutParams()
        if bounds.width != end:
            bounds.width = end
            scroll.setLayoutParams(bounds)

    class Layout(dynamic_proxy(View.OnLayoutChangeListener)):
        def onLayoutChange(self, widget, left, top, right, bottom, *previous):
            fit(right - left)

    root.addOnLayoutChangeListener(Layout())
    return fit


def sync(app, view, destination):
    adapter = app.native_host.adapter
    if adapter is None:
        return
    bar = app._impl.native.getSupportActionBar()
    if bar is None:
        return
    controls = getattr(view, '_native_reader_buttons', None)
    privacy = getattr(app, 'screen_privacy', None)
    if (getattr(app, '_reset_scheduled', False)
            or (privacy is not None and privacy.resume_locked)):
        controls = None
    if controls is None:
        adapter._reader_action_bar_keep_keyboard = False
        if getattr(adapter, '_reader_action_bar_active', False):
            release_buttons(adapter)
            adapter._reader_action_bar_title.setText('')
            adapter._reader_action_bar_title.setContentDescription('')
            adapter._reader_action_bar_status.setText('')
            adapter._reader_action_bar_status.setContentDescription('')
            bar.setCustomView(None)
            bar.setDisplayOptions(adapter._reader_action_bar_options)
            adapter._reader_action_bar_state = None
            adapter._reader_action_bar_active = False
        set_bar_visibility(adapter, bar, False)
        return

    from android.view import Gravity, View
    from android.graphics import Color
    from java import jclass
    from .workspace_navigation import detach
    from .control_icons import icon_button

    if not getattr(adapter, '_reader_action_bar_active', False):
        adapter._reader_action_bar_options = bar.getDisplayOptions()
    adapter._reader_action_bar_active = True
    adapter._reader_action_bar_keep_keyboard = bool(getattr(view, '_keyboard_actions_required', False))
    frame = getattr(view, '_workspace_frame', None)
    menu = frame.menu if frame is not None else getattr(view, '_workspace_menu_button', None)
    leading = []
    close = getattr(view, '_reader_close_button', None)
    if close is not None:
        leading.append(close)
    elif app.routes.screens[destination]:
        if not hasattr(adapter, '_reader_back'):
            adapter._reader_back = icon_button('back', 'Go back', on_press=lambda widget, **kw: app.routes.back())
        leading.append(adapter._reader_back)
    if menu is not None:
        leading.append(menu)
    from .reader_chrome import reader_buttons
    buttons = reader_buttons(app, view)
    title = getattr(view, '_native_reader_title', '')
    title = str(title() if callable(title) else title).replace('\n', ' ')
    state = (id(view), tuple(id(button) for button in [*leading, *buttons]))
    if getattr(adapter, '_reader_action_bar_state', None) != state:
        release_buttons(adapter)
        from commonUtils.ui.native.bars import android_bar
        def native_control(button):
            detach(button)
            button.app, button.window = app, app.main_window
            return button._impl.native
        root, label, status = android_bar(app._impl.native, leading, buttons, native_control=native_control)
        notes_controls = getattr(view, '_notes_title_controls', ())
        if notes_controls:
            from android.graphics import Typeface
            label.setTypeface(label.getTypeface(), Typeface.BOLD)
        if hasattr(view, '_document_path'):
            from .document_location import bind_android_hold
            adapter._reader_action_bar_fit = fit_document_title(
                root, label, len(leading), len(buttons), notes_controls=notes_controls)
            bind_android_hold(view, label.getParent())
        bar.setCustomView(root, jclass('androidx.appcompat.app.ActionBar$LayoutParams')(-1, -1))
        bar.setDisplayOptions(16)  # DISPLAY_SHOW_CUSTOM; title/actions live in one row.
        toolbar = root.getParent()
        if notes_controls and isinstance(toolbar, jclass('androidx.appcompat.widget.Toolbar')):
            adapter._reader_action_bar_insets = toolbar, toolbar.getContentInsetStart(), toolbar.getContentInsetEnd()
            inset = round(4 * root.getResources().getDisplayMetrics().density)
            toolbar.setContentInsetsRelative(inset, inset)
        adapter._reader_action_bar_title = label
        adapter._reader_action_bar_status = status
        adapter._reader_action_bar_buttons = [*leading, *buttons]
        adapter._reader_action_bar_state = state
    label = adapter._reader_action_bar_title
    if getattr(view, '_notes_title_controls', ()) and adapter._reader_action_bar_fit is not None:
        adapter._reader_action_bar_fit(label.getParent().getParent().getWidth())
    if hasattr(view, '_document_path'):
        from commonUtils.ui.native.panning_title import configure_android_title
        configure_android_title(label)
    if str(label.getText()) != title:
        label.setText(title)
    label.setContentDescription(title)
    dark = app._impl.native.getResources().getConfiguration().uiMode & 0x30 == 0x20
    label.setTextColor(Color.parseColor(android_palette(dark)['text']))
    status = adapter._reader_action_bar_status
    message = getattr(getattr(view, '_native_reader_status', None), 'text', '')
    prompt = message if message.lower().startswith(('save failed', 'cannot ', 'unsaved changes:',
        'book import failed', 'could not ')) else ''
    status.setText(prompt)
    status.setContentDescription(prompt)
    status.setTextColor(Color.parseColor(android_palette(dark)['text']))
    status.setVisibility(View.VISIBLE if prompt else View.GONE)
    from .document_location import mount_android_subtitle
    mount_android_subtitle(view, status, dark=dark)
    detach(view._native_reader_toolbar)
    for control in getattr(view, '_native_reader_hidden', ()):
        detach(control)
    if frame is not None:
        detach(frame.header)
    set_bar_visibility(adapter, bar, not getattr(view, '_reader_fullscreen', False))
