"""Native browser location header and status labels."""
from pathlib import PurePosixPath

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from commonUtils.ui.native.panning_title import PanningTitleLabel

from .appearance import accessible_name, surface, template_icon
from .control_icons import apply_icon
from .hub_icons import icon


def browser_command(button):
    """Use normal accent navigation, retaining outlines for Android E Ink."""
    return surface(button, radius=8, background='transparent', foreground='accent',
                   outlined=False, eink_outlined=True)


class BrowserStatusLabel(toga.Label):
    """Plain browser text with the value interface used by workflow status."""
    def __init__(self, value='', *, shrink=True, **kwargs):
        super().__init__(value, **kwargs)
        self.style.flex = 1
        self.style.margin_left = 6
        self.style.margin_right = 8
        backend = type(self._impl).__module__
        if backend.startswith('toga_iOS.'):
            self._impl.native.lineBreakMode = 5  # Middle ellipsis for long folder names.
        elif backend.startswith('toga_android.'):
            from android.text import TextUtils
            self._impl.native.setSingleLine(True)
            self._impl.native.setEllipsize(TextUtils.TruncateAt.MIDDLE)
        surface(self, radius=0, background='transparent', foreground='text',
                outlined=False, eink_outlined=False)
        if shrink:
            from commonUtils.ui.native.presentation import allow_label_to_shrink
            allow_label_to_shrink(self)

    @property
    def value(self):
        return self.text

    @value.setter
    def value(self, value):
        self.text = value
        changed = getattr(self, 'status_changed', None)
        if changed is not None:
            changed()


class FolderNameLabel(PanningTitleLabel, BrowserStatusLabel):
    """Browser caption styling with shared overflow motion."""


class FolderLocationHeader(toga.Box):
    """Current storage identity and a Back control."""
    def __init__(self, status, parent_button, *, actions=()):
        self.parent_button = parent_button
        self.folder_name = FolderNameLabel('Root', shrink=False, style=Pack(font_size=18, font_weight='normal'))
        self.status = status
        self.folder_name.style.flex = self.status.style.flex = 0
        self.folder_name.style.margin_left = self.status.style.margin_left = 0
        self.status.style.font_size = self.folder_name.style.font_size * .75
        # Let native font metrics (including Android font scaling/padding)
        # determine text height. Only the decorative icons have a fixed size.
        del self.status.style.height
        self.status.style.margin = 0
        surface(self.status, radius=0, background='transparent', foreground='muted',
                outlined=False, eink_outlined=False)
        self.storage_icons = toga.Box(style=Pack(direction=ROW, align_items=CENTER, height=18))
        self.storage_identity = toga.Box(style=Pack(direction=ROW, align_items=CENTER))
        self.caption = toga.Box(children=[self.folder_name],
                                style=Pack(direction=COLUMN, flex=1, margin_left=6))
        self.status.status_changed = self.refresh_status
        self.refresh_status()
        super().__init__(children=[parent_button, self.caption, *actions],
                         style=Pack(direction=ROW, align_items=CENTER, margin_top=0))
        if type(self._impl).__module__.startswith('toga_android.'):
            from .document_location import bind_android_hold
            self.use_android_title()
            bind_android_hold(self, self.folder_name._impl.native, type(self).show_location)
        elif type(self._impl).__module__.startswith('toga_iOS.'):
            from .document_location import bind_apple_hold
            bind_apple_hold(self, self.folder_name._impl.native, type(self).show_location)
        self.update('')

    def use_android_title(self):
        """Match the compact centered iOS identity without changing touch targets."""
        self._android_title = True
        self.folder_name.style.font_size = 17
        self.status.style.font_size = 17 * .75
        self.folder_name.style.text_align = self.status.style.text_align = CENTER
        self.folder_name.style.margin_right = 0
        self.storage_icons.style.height = 15
        self.balance_android_title()

    def balance_android_title(self):
        if self.caption not in self.children:
            return
        if not hasattr(self, '_title_gutters'):
            self._title_gutters = [toga.Box(style=Pack(width=0)), toga.Box(style=Pack(width=0))]
            super().insert(1, self._title_gutters[0])
            super().add(self._title_gutters[1])
        def action_width(child):
            width = child.style.width
            # Drawer buttons can use Pack's 'none' width. Use the standard
            # touch target when there is no explicit numeric action width.
            return width if isinstance(width, (int, float)) and width > 0 else 48
        trailing = sum(action_width(child) for child in self.children
                       if child not in (self.parent_button, self.caption, *self._title_gutters))
        leading = action_width(self.parent_button)
        self.caption.style.margin_left = self.caption.style.margin_right = 0
        self._title_gutters[0].style.width = max(0, trailing - leading)
        self._title_gutters[1].style.width = max(0, leading - trailing)

    def add(self, *children):
        super().add(*children)
        if getattr(self, '_android_title', False):
            self.balance_android_title()

    def remove(self, *children):
        super().remove(*children)
        if getattr(self, '_android_title', False):
            self.balance_android_title()

    def use_native_title(self):
        """Let UIKit own the title/actions; reserve content space only for search."""
        if getattr(self, 'native_actions', None) is not None:
            return
        self.title_actions = tuple(child for child in self.children
                                   if child not in (self.parent_button, self.caption))
        for child in list(self.children):
            self.remove(child)
        self.caption.remove(self.folder_name)
        self.caption.style.flex = 0
        self.caption.style.margin_left = 0
        self.status.style.text_align = CENTER
        self.style.margin_top = 0
        self.center_storage_identity()
        self.style.direction = COLUMN
        del self.style.align_items
        self.native_actions = toga.Box(style=Pack(direction=ROW, align_items=CENTER))
        self.add(self.caption)

    def center_storage_identity(self):
        # Equal flexible gutters center the icon/text group within the row.
        if not hasattr(self, '_identity_gutters'):
            self._identity_gutters = [toga.Box(style=Pack(flex=1)), toga.Box(style=Pack(flex=1))]
        for gutter in self._identity_gutters:
            if gutter in self.storage_identity.children:
                self.storage_identity.remove(gutter)
        self.storage_identity.children[-1].style.flex = 0
        del self.storage_identity.children[-1].style.width
        self.storage_identity.insert(0, self._identity_gutters[0])
        self.storage_identity.add(self._identity_gutters[1])

    def refresh_status(self):
        """Use one secondary line for operation text or passive storage identity."""
        if getattr(self, '_native_title_mounted', False):
            if self.status.text and self.caption not in self.children:
                self.insert(0, self.caption)
            elif not self.status.text and self.caption in self.children:
                self.remove(self.caption)
        visible = self.status if self.status.text else self.storage_identity
        for child in (self.status, self.storage_identity):
            if child is not visible and child in self.caption.children:
                self.caption.remove(child)
        if visible not in self.caption.children:
            self.caption.add(visible)

    def clear_location(self):
        self.folder_location = None
        if self.folder_name.value:
            self.folder_name.value = ''
        native_title = getattr(self, '_folder_title_view', None)
        if native_title is not None:
            native_title.hidden = True
            self._folder_title_view = self._folder_title_state = None

    def show_location(self, *, name=None):
        from .document_location import show_location
        if self.folder_location:
            show_location(self, 'Folder location', f'{name or self.folder_name.value}\n\n{self.folder_location}')

    def update(self, path, *, remote=False, encrypted=False, unlocked=False, name=None, session_only=False, provider=None):
        from services.documents.storage import display_path
        previous_location = getattr(self, 'folder_location', None)
        self.folder_location = display_path(provider, path) if provider is not None else None
        title = name if name is not None else PurePosixPath(path).name if path else 'Root'
        if self.folder_name.value != title:
            self.folder_name.value = title
        elif self.folder_location and self.folder_location != previous_location:
            self.folder_name.restart_pan()
        apply_icon(self.parent_button, 'back', 'Back')
        browser_command(self.parent_button)
        kinds = [('storage_remote', 'Online folder')] if remote else [('storage_local', 'On-device folder')]
        if encrypted:
            state = 'unlocked' if unlocked else 'locked'
            kinds.append(('folder_' + state, 'Encrypted folder, ' + state))
        identity_key = (remote, encrypted, unlocked, session_only)
        if identity_key == getattr(self, '_identity_key', None):
            return
        for child in list(self.storage_icons.children):
            self.storage_icons.remove(child)
        for child in list(self.storage_identity.children):
            self.storage_identity.remove(child)
        self.storage_identity.add(self.storage_icons)
        for name, label in kinds:
            size = 12 if type(self._impl).__module__.startswith('toga_android.') else 18
            indicator = template_icon(toga.ImageView(icon(name), style=Pack(width=size, height=size, margin_right=4)))
            indicator.control_icon = name
            accessible_name(indicator, label)
            surface(indicator, radius=0, background='transparent',
                    foreground=name if name.startswith('folder_') else 'accent',
                    outlined=False, eink_outlined=False)
            self.storage_icons.add(indicator)
        identity = 'Cloud' if remote else 'On-device'
        if encrypted:
            state = 'Unlocked (Session Only)' if unlocked and session_only else 'Unlocked' if unlocked else 'Locked'
            identity += ' · ' + state
            if not remote:
                identity += ' · LocalCrypt'
        self.storage_identity.add(BrowserStatusLabel(identity, style=Pack(
            font_size=self.folder_name.style.font_size * .75, margin=0)))
        surface(self.storage_identity.children[-1], radius=0, background='transparent', foreground='muted',
                outlined=False, eink_outlined=False)
        if type(self._impl).__module__.startswith('toga_android.'):
            self.center_android_identity(identity)
        elif getattr(self, 'native_actions', None) is not None:
            self.center_storage_identity()
        self._storage_kinds = kinds
        self._identity_key = identity_key

    def center_android_identity(self, identity):
        """Center icons with their caption as one ellipsizing native text run."""
        from android.text import SpannableString
        from android.text.style import ImageSpan
        label = self.storage_identity.children[-1]
        label.style.margin = 0
        label.style.text_align = CENTER
        # Inline spans keep the complete icon/text group centered. Separate
        # flexible labels either strand icons at the edge or hide long text.
        text = SpannableString('\ufffc ' * len(self.storage_icons.children) + identity)
        for index, image in enumerate(self.storage_icons.children):
            drawable = image._impl.native.getDrawable()
            size = round(image._impl.scale_in(12))
            drawable.setBounds(0, 0, size, size)
            text.setSpan(ImageSpan(drawable, 1), index * 2, index * 2 + 1, 33)
        self.storage_identity.remove(self.storage_icons)
        label._impl.native.setText(text)
        label._impl.native.setContentDescription(', '.join(
            image.accessible_name for image in self.storage_icons.children) + '. ' + identity)

    def update_provider(self, path, provider, *, name=None):
        provider = getattr(provider, 'provider', provider)
        remote = getattr(provider, 'remote_storage', False)
        encrypted = bool(getattr(provider, 'private', False))
        if not path and encrypted and not remote:
            name = getattr(provider, 'remote', name)
        self.update(path, remote=remote, encrypted=encrypted, unlocked=True,
                    name=name, session_only=provider_session_only(provider), provider=provider)


def provider_session_only(provider):
    """Read the loaded credential publication without querying the bridge."""
    provider = getattr(provider, 'provider', provider)
    remote = getattr(provider, 'remote', None)
    records = getattr(getattr(provider, 'client', None), 'package_records', ())
    return any(remote in record.get('remotes', ()) and not record.get('saved', False)
               for record in records)
