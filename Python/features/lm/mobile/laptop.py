"""Retained chat panes positioned around an active horizontal reserved region."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW


def chat_region(owner):
    widget = owner.chat_workspace
    if not type(widget._impl).__module__.startswith('toga_iOS.'):
        return None
    bounds = widget._impl.native.bounds.size
    for region in owner.presentation.reserved_divisions(widget):
        # A software keyboard can cover the lower half of an active fold.
        # Keep recognizing that posture when the division leaves the viewport.
        if not region.vertical and region.x <= 1 and region.x + region.width >= float(bounds.width) - 1 and region.y > 0:
            return float(bounds.height), region.y, region.height
    return None



def docked_keyboard_top(owner, native):
    """Return the physical keyboard edge in the given UIKit view's coordinates."""
    adapter = owner.native_host.adapter
    frame = getattr(adapter, 'keyboard_frame', None)
    if not getattr(adapter, 'keyboard_visible', False) or frame is None:
        return None
    window = owner.main_window._impl.native
    keyboard = window.convertRect(frame, fromCoordinateSpace=window.screen.coordinateSpace)
    if keyboard.origin.y + keyboard.size.height < window.bounds.size.height - 1:
        return None
    keyboard = native.convertRect(keyboard, fromView=window)
    if keyboard.origin.x < native.bounds.size.width and keyboard.origin.x + keyboard.size.width > 0:
        return float(keyboard.origin.y)
    return None


def visible_height(owner, height):
    """Clip the fold allocation even before UIKit settles its safe area."""
    native = getattr(owner.chat_workspace._impl, 'native', None)
    top = docked_keyboard_top(owner, native) if native is not None else None
    return height if top is None else max(0, min(height, top - 8))


def allocation(height, seam, gap, status=0):
    """Fit a lower deck, or keep a compact composer wholly above the crease."""
    lower = height - seam - gap - 8
    if lower >= 168 + status:
        prompt = max(52, min(180, lower - 80 - status))
        return max(0, seam - 8), gap + 16, lower, prompt, True
    available = min(height, max(0, seam - 8))
    prompt = max(52, min(96, available / 4))
    deck = min(available, prompt + 24 + status)
    return max(0, available - deck), 0, deck, max(0, min(prompt, deck - 24 - status)), False


def mount(parent, children):
    if list(parent.children) == children:
        return
    for child in list(parent.children):
        if child not in children:
            parent.remove(child)
    for index, child in enumerate(children):
        if index < len(parent.children) and parent.children[index] is child:
            continue
        if child.parent is not None:
            child.parent.remove(child)
        parent.insert(index, child)


class LaptopChat:
    def __init__(self, owner):
        self.active = False
        self.prompt_height = None
        self.gap = toga.Box(style=Pack(height=0))
        self.space = toga.Box(style=Pack(flex=1))
        self.deck = toga.Box(style=Pack(direction=COLUMN))
        self.history = toga.Button('Conversations', on_press=owner.toggle_chat_conversations, style=Pack(flex=1, height=44))
        self.tools = toga.Box(children=[self.history,
            owner.presentation.icon_button('compose', 'New conversation', on_press=owner.new_chat),
            owner.presentation.icon_button('preferences', 'Chat settings', on_press=owner.show_chat_configuration)],
            style=Pack(direction=ROW, margin_bottom=8))

    def reflow(self, owner):
        geometry = chat_region(owner)
        if geometry is None:
            if self.active:
                self.active = False
                owner.chat_drawer_open = self.saved_drawer
                mount(owner.chat_workspace, [])
                mount(self.deck, [])
                mount(owner.chat_messages, [owner.chat_transcript_card, owner.chat_status_box, owner.chat_composer])
                owner.chat_transcript_card.style.flex = 1
                del owner.chat_transcript_card.style.height
                owner.chat_workspace.style.direction = ROW
                self.prompt_height = None
            return False
        if not self.active:
            self.saved_drawer = owner.chat_drawer_open
            owner.chat_drawer_open = False
            self.active = True
        status = 48 if owner.chat_status_box.children and not owner.chat_compact_keyboard else 0
        height, seam, band = geometry
        upper, gap, lower, prompt, tools = allocation(visible_height(owner, height), seam, band, status)
        if not tools:
            owner.chat_drawer_open = False
        self.prompt_height = prompt
        owner.chat_workspace.style.direction = COLUMN
        owner.chat_messages.style.margin_left = 0
        owner.chat_transcript_card.style.flex = 0
        owner.chat_transcript_card.style.height = upper
        self.gap.style.height = gap
        self.deck.style.height = lower
        self.history.text = 'Back to draft' if owner.chat_drawer_open else 'Conversations'
        if owner.chat_drawer_open:
            owner.chat_sidebar.style.flex = 1
            del owner.chat_sidebar.style.width
            lower_children = [self.tools, owner.chat_sidebar]
        else:
            lower_children = ([self.tools] if tools else []) + [self.space, owner.chat_status_box, owner.chat_composer]
        mount(self.deck, lower_children)
        mount(owner.chat_workspace, [owner.chat_transcript_card, self.gap, self.deck])
        return True
