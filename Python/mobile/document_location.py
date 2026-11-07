"""Storage identity rows using the same icon and caption roles as file browsing."""
import toga
from toga.style import Pack
from toga.style.pack import ROW
from .appearance import surface, template_icon, accessible_name
from .hub_icons import icon
from .browser_ui import BrowserStatusLabel


def storage_identity(copies=None, reader=None):
    from services.documents.storage import document_sources, DocumentPolicy, document_writable
    sources = tuple(document_sources(copies))
    resource = getattr(copies, 'resource', None)
    if resource is not None:
        sources += (resource,)
    remote = any(getattr(source, 'remote_storage', False) for source in sources)
    private = copies is not None and not DocumentPolicy.for_provider(copies).persistent
    encrypted = any(getattr(source, 'encrypted', False) for source in sources) or (private and not remote)
    label = next((getattr(source, 'storage_label') for source in sources
                  if getattr(source, 'storage_label', None)), 'Cloud' if remote else 'On-device')
    parts = [label]
    if encrypted:
        parts.append('Unlocked')
        if not remote:
            parts.append('Encrypted Copy')
    if any(getattr(source, 'session_only', False) for source in sources) or private and not remote:
        parts.append('🕵️ Session-Only')
    if not document_writable(copies, reader):
        parts.append('(Read-Only)')
    return ' · '.join(parts), remote, encrypted


def install_document_location(view, *, copies=None, reader=None):
    existing = getattr(view, '_document_location_row', None)
    if existing is not None and existing in view.children:
        view.remove(existing)
    text, remote, encrypted = storage_identity(copies, reader)
    row = toga.Box(style=Pack(direction=ROW, align_items='center', margin_left=6, margin_right=6, margin_bottom=4))
    kinds = [('storage_remote' if remote else 'storage_local', 'Online folder' if remote else 'On-device folder')]
    if encrypted:
        kinds.append(('folder_unlocked', 'Encrypted folder, unlocked'))
    row.add(toga.Box(style=Pack(flex=1)))
    for name, label in kinds:
        indicator = template_icon(toga.ImageView(icon(name), style=Pack(width=12, height=12, margin_right=4)))
        accessible_name(indicator, label)
        surface(indicator, radius=0, background='transparent', foreground=name if name.startswith('folder_') else 'accent',
                outlined=False, eink_outlined=False)
        row.add(indicator)
    caption = BrowserStatusLabel(text, style=Pack(font_size=17 * .75, margin=0))
    accessible_name(caption, text)
    surface(caption, radius=0, background='transparent', foreground='muted', outlined=False, eink_outlined=False)
    row.add(caption)
    row.add(toga.Box(style=Pack(flex=1)))
    view.insert(0, row)
    frame = getattr(view, '_reading_frame_owner', None)
    if frame is not None:
        if existing in frame.controls:
            frame.controls.remove(existing)
            frame.top_controls -= 1
        frame.controls.insert(0, row)
        frame.top_controls += 1
    view._document_location_row = row
    view._document_storage_status = text
    view._document_storage_kinds = kinds


def remove_location_row(view):
    """The native subtitle replaces the content row, including after fullscreen."""
    row = getattr(view, '_document_location_row', None)
    if row is None:
        return
    if row.parent is not None:
        row.parent.remove(row)
    frame = getattr(view, '_reading_frame_owner', None)
    if frame is not None and row in frame.controls:
        frame.controls.remove(row)
        frame.top_controls -= 1


def side_title_header(view):
    header = getattr(view, '_document_title_header', None)
    parent = getattr(view, '_document_title_parent', view)
    return header if header is not None and header.parent is parent else None


def side_title_reader(view):
    if side_title_header(view) is not None:
        return view
    for child in getattr(view, 'children', ()):
        reader = side_title_reader(child)
        if reader is not None:
            return reader
    return None


def empty_bar_title():
    from rubicon.objc import ObjCClass
    placeholder = ObjCClass('UIView').alloc().init()
    placeholder.accessibilityElementsHidden = True
    return placeholder


def place_title_in_header(header, title, subtitle):
    from .folder_title import storage_title_height
    # UIKit may have compressed this view in a previous navigation bar.
    # Reserve its designed height before attaching or reusing it in the reader.
    content = getattr(header, '_title_content', header)
    height = max(48, storage_title_height(subtitle), content.style.height or 0) if content is not header else storage_title_height(subtitle)
    if header.style.height != height:
        header.style.height = height
    host = content._impl.native
    if title.superview == host:
        return
    previous = getattr(header, '_mounted_title', None)
    if previous is not None and previous != title:
        # UIKit can reparent a retained title during adaptive bar changes.
        # Retire the previous title even when its current superview has moved.
        previous.removeFromSuperview()
    host.addSubview(title)
    title.frame = host.bounds
    title.autoresizingMask = 2 | 16  # Flexible width and height.
    header._mounted_title = title


def show_location(view, title, location):
    window = view.window
    if window is None:
        return
    if location:
        view.app.loop.create_task(window.dialog(toga.InfoDialog(title, str(location))))


def show_document_path(view):
    if view.window is not None:
        show_location(view, 'Document location', view._document_path())


_apple_hold_target = None


def bind_apple_hold(view, native, callback=show_document_path):
    from rubicon.objc import ObjCClass, SEL, objc_method
    from weakref import ref
    global _apple_hold_target
    if _apple_hold_target is None:
        class LogisticsDocumentTitleHold(ObjCClass('NSObject')):
            @objc_method
            def hold_(self, gesture) -> None:
                owner = self.owner()
                if owner is not None and int(gesture.state) == 1:
                    self.callback(owner)
        _apple_hold_target = LogisticsDocumentTitleHold
    target = _apple_hold_target.alloc().init()
    target.owner = ref(view)
    target.callback = callback
    gesture = ObjCClass('UILongPressGestureRecognizer').alloc().initWithTarget(target, action=SEL('hold:'))
    native.userInteractionEnabled = True
    native.addGestureRecognizer(gesture)
    view._title_hold_target = target


def bind_android_hold(view, label, callback=show_document_path):
    from android.view import View
    from java import dynamic_proxy
    from weakref import ref
    owner = ref(view)
    class Hold(dynamic_proxy(View.OnLongClickListener)):
        def onLongClick(self, widget):
            current = owner()
            if current is not None:
                callback(current)
            return True
    label.setOnLongClickListener(Hold())


def mount_apple_title(view, controller, title):
    if not hasattr(view, '_document_storage_status') and not hasattr(view, '_document_path'):
        controller.navigationItem.titleView = None
        return
    band = getattr(view, '_reader_top_band_state', None)
    if band is not None and band['controller'] != controller:
        from .reader_top_band import restore
        restore(view)
        band = None
    from .folder_title import storage_title, storage_title_height
    from .ios_toolbar import vertical_edge
    edge = vertical_edge(controller)
    tools = getattr(view, '_native_drawing_tools', None)
    controls = getattr(view, '_document_title_controls', ())
    notes_controls = getattr(view, '_notes_title_controls', ())
    if notes_controls:
        close = notes_controls[0]
        controls = notes_controls[1:] if edge else notes_controls
        view._document_title_controls = controls
    compact_tools = tools is not None and not controls and band is None and tools.fits(controller)
    wide_notebook = (tools is not None and not controls and band is None
                     and not getattr(view, '_reader_fullscreen', False) and tools.wide_phone(controller))
    leading = compact_tools or wide_notebook
    if tools is not None and not compact_tools and tools.header is not None:
        tools.close()
    bounds = controller.view.bounds.size
    available = float(bounds.width) or float(view.window._impl.native.bounds.size.width)
    if notes_controls:
        view._notes_compact_title = not edge and available < 600
    control_widths = (button.style.width for button in controls)
    gutters = ((32 if edge else 16) + sum((width if isinstance(width, (int, float)) else 48) + 8
                                        for width in control_widths)
               if controls else (32 if edge else 216))
    width = max(44, available - gutters)
    state = (title, getattr(view, '_document_storage_status', ''), tuple(getattr(view, '_document_storage_kinds', ())), width, leading)
    changed = getattr(view, '_document_title_state', None) != state
    if changed:
        view._document_title_view = storage_title(title, state[1], state[2], width,
                                                  leading=leading, bold=bool(notes_controls),
                                                  title_size=getattr(view, '_native_reader_title_size', 17))
        if hasattr(view, '_document_path'):
            bind_apple_hold(view, view._document_title_view)
        view._document_title_state = state
    remove_location_row(view)
    if band is not None:
        # Title refresh also runs independently of toolbar projection. The
        # active content owner stays authoritative until project() retires it.
        header = band['header']
        row = header.children[0]
        view._document_title_header = header
        if controller.navigationItem.titleView is not None:
            controller.navigationItem.titleView = None
        frame = getattr(view, '_reading_frame_owner', None)
        if frame is not None and header not in frame.controls:
            frame.controls.insert(0, header)
            frame.top_controls += 1
        if not getattr(view, '_reader_fullscreen', False):
            if header.parent is not view:
                if header.parent is not None:
                    header.parent.remove(header)
                view.insert(0, header)
            place_title_in_header(row, view._document_title_view, state[1])
        return
    header = getattr(view, '_document_title_header', None)
    was_mounted = side_title_header(view) is not None
    frame = getattr(view, '_reading_frame_owner', None)
    if controls or leading or (edge and (frame is not None or hasattr(view, '_document_path'))):
        # UIKit owns the side actions, but can reposition its titleView after
        # content layout. Give the actual title its own row above the page.
        if header is None:
            top = 0 if notes_controls else 6
            header = view._document_title_header = toga.Box(style=Pack(margin_top=top, margin_bottom=6))
            header._empty_bar_title = empty_bar_title()
            if controls:
                header.style.direction = ROW
                header.style.align_items = 'center'
                header.style.margin_left = header.style.margin_right = 8
                header._title_content = toga.Box(style=Pack(flex=1, height=max(48, storage_title_height(state[1])), margin_left=8, margin_right=8))
                for button in controls:
                    if button.parent is not None:
                        button.parent.remove(button)
                header.add(*controls[:-1], header._title_content, controls[-1])
        if notes_controls:
            inset = 4 if view._notes_compact_title else 8
            if header.style.margin_left != inset:
                header.style.margin_left = header.style.margin_right = inset
                header._title_content.style.margin_left = header._title_content.style.margin_right = inset
            if edge and close.parent is header:
                header.remove(close)
            elif not edge and close.parent is not header:
                if close.parent is not None:
                    close.parent.remove(close)
                header.insert(0, close)
        if controls:
            header._title_content.style.height = max(48, storage_title_height(state[1]))
        if controller.navigationItem.titleView != header._empty_bar_title:
            controller.navigationItem.titleView = header._empty_bar_title
        if frame is not None and header not in frame.controls:
            frame.controls.insert(0, header)
            frame.top_controls += 1
        if not getattr(view, '_reader_fullscreen', False):
            if not was_mounted:
                getattr(view, '_document_title_parent', view).insert(0, header)
            if compact_tools:
                tools.mount(header, controller)
            place_title_in_header(header, view._document_title_view, state[1])
        elif was_mounted:
            header.parent.remove(header)
    else:
        if frame is not None and header in frame.controls:
            frame.controls.remove(header)
            frame.top_controls -= 1
        if was_mounted:
            header.parent.remove(header)
        if getattr(controller.navigationItem, 'titleView', None) != view._document_title_view:
            controller.navigationItem.titleView = view._document_title_view
    if was_mounted != (side_title_header(view) is not None):
        container = getattr(view._impl, 'container', None)
        if container is not None:
            view.app.native_host.adapter.layout_content(container)


def mount_android_subtitle(view, status, *, dark):
    """Place storage icons and caption together below Android's centered title."""
    if not hasattr(view, '_document_storage_status'):
        return
    from android.view import Gravity, View
    from android.widget import LinearLayout, ImageView, TextView
    from android.graphics import Color
    from .palette import android_palette
    parent = status.getParent()
    previous = getattr(view, '_android_storage_subtitle', None)
    state = (status, view._document_storage_status, tuple(view._document_storage_kinds), dark)
    if getattr(view, '_android_storage_state', None) != state:
        if previous is not None and previous.getParent() is not None:
            previous.getParent().removeView(previous)
        context = status.getContext()
        row = LinearLayout(context)
        row.setGravity(Gravity.CENTER)
        density = row.getResources().getDisplayMetrics().density
        colors = android_palette(dark)
        for name, label in view._document_storage_kinds:
            image = ImageView(context)
            image.setImageBitmap(icon(name)._impl.native)
            image.setColorFilter(Color.parseColor(colors['accent']))
            image.setContentDescription(label)
            params = LinearLayout.LayoutParams(round(12 * density), round(12 * density))
            params.rightMargin = round(4 * density)
            row.addView(image, params)
        caption = TextView(context)
        caption.setSingleLine(True)
        from commonUtils.ui.readers.layout import READER_LAYOUT
        caption.setTextSize(READER_LAYOUT.caption_size)
        caption.setTextColor(Color.parseColor(colors['muted']))
        caption.setText(view._document_storage_status)
        row.addView(caption, LinearLayout.LayoutParams(-2, -2))
        parent.addView(row, LinearLayout.LayoutParams(-1, -2))
        view._android_storage_subtitle = row
        view._android_storage_state = state
    view._android_storage_subtitle.setVisibility(View.GONE if status.getVisibility() == View.VISIBLE else View.VISIBLE)
    remove_location_row(view)
