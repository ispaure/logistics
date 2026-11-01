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
            parts.append('LocalCrypt')
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
    return header if header is not None and header.parent is view else None


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


def place_title_in_header(header, title):
    host = header._impl.native
    if title.superview == host:
        return
    previous = getattr(header, '_mounted_title', None)
    if previous is not None and previous.superview == host:
        previous.removeFromSuperview()
    from math import ceil
    header.style.height = ceil(float(title.bounds.size.height))
    host.addSubview(title)
    title.frame = host.bounds
    title.autoresizingMask = 2 | 16  # Flexible width and height.
    header._mounted_title = title


def mount_apple_title(view, controller, title):
    if not hasattr(view, '_document_storage_status'):
        controller.navigationItem.titleView = None
        return
    from .folder_title import storage_title
    from .ios_toolbar import vertical_edge
    edge = vertical_edge(controller)
    bounds = controller.view.bounds.size
    width = float(bounds.width) or float(view.window._impl.native.bounds.size.width)
    width = max(44, width - (32 if edge else 216))
    state = (title, view._document_storage_status, tuple(view._document_storage_kinds), width)
    changed = getattr(view, '_document_title_state', None) != state
    if changed:
        view._document_title_view = storage_title(title, state[1], state[2], width)
        view._document_title_state = state
    remove_location_row(view)
    header = getattr(view, '_document_title_header', None)
    was_mounted = side_title_header(view) is not None
    frame = getattr(view, '_reading_frame_owner', None)
    side = edge and frame is not None
    if side:
        # UIKit owns the side actions, but can reposition its titleView after
        # content layout. Give the actual title its own row above the page.
        if header is None:
            header = view._document_title_header = toga.Box(style=Pack(margin_top=6, margin_bottom=6))
            header._empty_bar_title = empty_bar_title()
        if controller.navigationItem.titleView != header._empty_bar_title:
            controller.navigationItem.titleView = header._empty_bar_title
        if header not in frame.controls:
            frame.controls.insert(0, header)
            frame.top_controls += 1
        if not getattr(view, '_reader_fullscreen', False):
            if not was_mounted:
                view.insert(0, header)
            place_title_in_header(header, view._document_title_view)
        elif was_mounted:
            view.remove(header)
    else:
        if frame is not None and header in frame.controls:
            frame.controls.remove(header)
            frame.top_controls -= 1
        if was_mounted:
            view.remove(header)
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
