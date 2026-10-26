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
    row = toga.Box(style=Pack(direction=ROW, margin_left=6, margin_right=6, margin_bottom=4))
    kinds = [('storage_remote' if remote else 'storage_local', 'Online folder' if remote else 'On-device folder')]
    if encrypted:
        kinds.append(('folder_unlocked', 'Encrypted folder, unlocked'))
    for name, label in kinds:
        indicator = template_icon(toga.ImageView(icon(name), style=Pack(width=16, height=16, margin_right=4)))
        accessible_name(indicator, label)
        surface(indicator, radius=0, background='transparent', foreground=name if name.startswith('folder_') else 'accent',
                outlined=False, eink_outlined=False)
        row.add(indicator)
    caption = BrowserStatusLabel(text, style=Pack(font_size=12, margin=0, flex=1))
    accessible_name(caption, text)
    surface(caption, radius=0, background='transparent', foreground='muted', outlined=False, eink_outlined=False)
    row.add(caption)
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
