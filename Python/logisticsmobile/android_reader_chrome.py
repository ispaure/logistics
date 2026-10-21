"""Mount existing document controls in Android's single native action bar."""
from .palette import android_palette


def release_buttons(adapter):
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
            bar.hide()
            return
    bar.show() if visible else bar.hide()


def sync(app, view, destination):
    adapter = app.native_host.adapter
    bar = app._impl.native.getSupportActionBar()
    if bar is None:
        return
    controls = getattr(view, '_native_reader_buttons', None)
    privacy = getattr(app, 'screen_privacy', None)
    if (getattr(app, '_reset_scheduled', False)
            or (privacy is not None and privacy.saved_content is not None)):
        controls = None
    if controls is None:
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
    from android.widget import FrameLayout, LinearLayout, TextView
    from android.text import TextUtils
    from android.graphics import Color
    from java import jclass
    from .workspace_navigation import detach
    from .control_icons import icon_button

    if not getattr(adapter, '_reader_action_bar_active', False):
        adapter._reader_action_bar_options = bar.getDisplayOptions()
    adapter._reader_action_bar_active = True
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
        root = FrameLayout(app._impl.native)
        density = root.getResources().getDisplayMetrics().density
        size = round(48 * density)
        label = TextView(app._impl.native)
        label.setSingleLine(True)
        label.setEllipsize(TextUtils.TruncateAt.MIDDLE)
        label.setGravity(Gravity.CENTER)
        label.setTextSize(17)
        status = TextView(app._impl.native)
        status.setSingleLine(True)
        status.setEllipsize(TextUtils.TruncateAt.MIDDLE)
        status.setGravity(Gravity.CENTER)
        status.setTextSize(12)
        titles = LinearLayout(app._impl.native)
        titles.setOrientation(1)
        titles.setGravity(Gravity.CENTER)
        titles.addView(label, LinearLayout.LayoutParams(-1, -2))
        titles.addView(status, LinearLayout.LayoutParams(-1, -2))
        params = FrameLayout.LayoutParams(-1, -1)
        params.leftMargin = params.rightMargin = max(len(leading), len(buttons)) * size
        root.addView(titles, params)
        for group, gravity in ((leading, Gravity.START), (buttons, Gravity.END)):
            native_group = LinearLayout(app._impl.native)
            native_group.setGravity(Gravity.CENTER_VERTICAL)
            root.addView(native_group, FrameLayout.LayoutParams(-2, -1, gravity))
            for button in group:
                detach(button)
                button.app, button.window = app, app.main_window
                native = button._impl.native
                parent = native.getParent()
                if parent is not None:
                    parent.removeView(native)
                native.setVisibility(View.VISIBLE)
                native_group.addView(native, LinearLayout.LayoutParams(size, -1))
        bar.setCustomView(root, jclass('androidx.appcompat.app.ActionBar$LayoutParams')(-1, -1))
        bar.setDisplayOptions(16)  # DISPLAY_SHOW_CUSTOM; title/actions live in one row.
        adapter._reader_action_bar_title = label
        adapter._reader_action_bar_status = status
        adapter._reader_action_bar_buttons = [*leading, *buttons]
        adapter._reader_action_bar_state = state
    label = adapter._reader_action_bar_title
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
    detach(view._native_reader_toolbar)
    for control in getattr(view, '_native_reader_hidden', ()):
        detach(control)
    if frame is not None:
        detach(frame.header)
    set_bar_visibility(adapter, bar, not getattr(view, '_reader_fullscreen', False))
