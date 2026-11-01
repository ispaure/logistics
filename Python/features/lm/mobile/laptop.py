"""Retained chat panes positioned around an active horizontal reserved region."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW


def chat_region(owner):
    from mobile.fold_layout import reserved_divisions
    widget = owner.chat_workspace
    if not type(widget._impl).__module__.startswith('toga_iOS.'):
        return None
    bounds = widget._impl.native.bounds.size
    for region in reserved_divisions(widget):
        # A software keyboard can cover the lower half of an active fold.
        # Keep recognizing that posture when the division leaves the viewport.
        if not region.vertical and region.x <= 1 and region.x + region.width >= float(bounds.width) - 1 and region.y > 0:
            return float(bounds.height), region.y, region.height
    return None



def visible_height(owner, height):
    """Clip to the docked keyboard even before UIKit settles its safe area."""
    adapter = owner.native_host.adapter
    if (not type(owner.chat_workspace._impl).__module__.startswith('toga_iOS.')
            or not getattr(adapter, 'keyboard_visible', False)
            or getattr(adapter, 'keyboard_frame', None) is None):
        return height
    native = owner.chat_workspace._impl.native
    window = owner.main_window._impl.native
    keyboard = window.convertRect(adapter.keyboard_frame, fromCoordinateSpace=window.screen.coordinateSpace)
    keyboard = native.convertRect(keyboard, fromView=window)
    if keyboard.origin.y + keyboard.size.height >= height - 1 and keyboard.size.width >= native.bounds.size.width - 1:
        return max(0, min(height, float(keyboard.origin.y) - 8))
    return height


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
        parent.remove(child)
    for child in children:
        if child.parent is not None:
            child.parent.remove(child)
        parent.add(child)


class LaptopChat:
    def __init__(self, owner):
        self.active = False
        self.prompt_height = None
        self.gap = toga.Box(style=Pack(height=0))
        self.space = toga.Box(style=Pack(flex=1))
        self.deck = toga.Box(style=Pack(direction=COLUMN))
        self.history = toga.Button('Conversations', on_press=owner.toggle_chat_conversations, style=Pack(flex=1, height=44))
        self.tools = toga.Box(children=[self.history,
            toga.Button('New chat', on_press=owner.new_chat, style=Pack(flex=1, height=44)),
            toga.Button('Model & settings', on_press=owner.show_chat_configuration, style=Pack(flex=1, height=44))],
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
        status = 48 if owner.chat_status_box.children else 0
        height, seam, band = geometry
        upper, gap, lower, prompt, tools = allocation(visible_height(owner, height), seam, band, status)
        if not tools:
            owner.chat_drawer_open = False
        self.prompt_height = prompt
        owner.chat_workspace.style.direction = COLUMN
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
