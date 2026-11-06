"""The mobile Workspaces root controls and retained source trees."""

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW

from commonUtils.ui.native.forms import FittedLabel

from .appearance import accessible_name, batch_surfaces
from .folder_hub import credential_choices, source_choices
from .folder_hub_style import (
    SOURCE_LABELS, folder_scroll, source_actions, source_tab, surface, toolbar_button,
)
from .folder_tree_view import FolderTreeView
from .ui_metrics import CAPTION_TEXT, CONTROL_TEXT, TOUCH_TARGET, toga_font_size


class WorkspacesScreen:
    """Present the root on the folder controller that owns its state."""

    def set_folder_loading(self, message='', *, busy=False):
        """Idle loading controls have no native view or reserved layout space."""
        self.folder_loading_status.text = message
        children = [self.folder_loading_status] if message else []
        if busy:
            children.append(self.folder_loading_progress)
        if list(self.folder_loading_box.children) != children:
            for child in list(self.folder_loading_box.children):
                self.folder_loading_box.remove(child)
            for child in children:
                self.folder_loading_box.add(child)

    def selected_folder_credential(self):
        try:
            selected = self.folder_credential.value
        except IndexError:
            # UIKit may still report the old row while credential items change.
            selected = getattr(self, 'folder_credential_name', 'All')
        return selected if selected in self.folder_credentials else 'All'

    def build_folder_picker(self, *, choices=None):
        # Finish discovery before replacing references to the visible controls.
        choices = self.folder_choices() if choices is None else choices
        self.folder_source = getattr(self, 'folder_source', 'Local')
        self._build_folder_source_tabs()
        self.folder_local_group = getattr(self, 'folder_local_group', self.preferences.values['workspace_local_group'])
        self.folder_local_styled = None
        self.folder_local_tabs = toga.Box(style=Pack(direction=ROW, margin_bottom=8))
        self.folder_local_buttons = {}
        for group in ('Rclone', 'Others'):
            def select_local(widget=None, selected=group, **kwargs):
                if self.folder_local_group != selected:
                    self.folder_credential_name = 'All'
                    self.folder_credential.on_change = None
                    self.folder_credential.value = 'All'
                    self.folder_credential.on_change = self.change_folder_credential
                self.folder_local_group = selected
                self.update_folder_list(self.folder_all_choices)
                try:
                    self.preferences.save(workspace_local_group=selected)
                except (OSError, ValueError) as error:
                    self.set_folder_loading('Could not remember workspace tab: ' + str(error))
            button = toga.Button(group, on_press=select_local,
                                 style=Pack(flex=1, height=TOUCH_TARGET, font_size=toga_font_size(CONTROL_TEXT)))
            self.folder_local_buttons[group] = button
            self.folder_local_tabs.add(button)
        self.folder_local_header = toga.Box(style=Pack(direction=COLUMN))
        self.folder_list = toga.Box(style=Pack(direction=COLUMN))
        self.folder_tab_views = {}
        self.folder_tab_snapshot = None
        self.folder_collapsed = getattr(self, 'folder_collapsed', set())
        self.folder_credentials = self.credential_groups(source_choices(choices,
            'Local' if self.folder_source == 'Local' else 'rclone', self.network_share_remotes(), local_group='Rclone'))
        selected = getattr(self, 'folder_credential_name', 'All')
        self.folder_credential = toga.Selection(items=list(self.folder_credentials),
            value=selected if selected in self.folder_credentials else 'All',
            style=Pack(flex=1, height=TOUCH_TARGET, font_size=toga_font_size(CONTROL_TEXT)))
        self.folder_credential.on_change = self.change_folder_credential
        accessible_name(self.folder_credential, 'Credential filter')
        if type(self.folder_credential._impl).__module__.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, CGRect
            native = self.folder_credential._impl.native
            image = ObjCClass('UIImage').systemImageNamed('chevron.down')
            accessory = ObjCClass('UIImageView').alloc().initWithImage(image)
            accessory.frame = CGRect((0, 0), (32, 20))
            accessory.contentMode = 4  # UIViewContentModeCenter
            accessory.tintColor = ObjCClass('UIColor').secondaryLabelColor()
            accessory.isAccessibilityElement = False
            native.rightView = accessory
            native.rightViewMode = 3  # UITextFieldViewModeAlways
            native.accessibilityHint = 'Opens the list of credentials'
        self.folder_transfers_button = toga.Button('Transfers', on_press=self.show_transfers, style=Pack(height=TOUCH_TARGET, font_size=toga_font_size(CONTROL_TEXT), flex=1))
        toolbar_button(self.folder_transfers_button, 'arrow.up.arrow.down')
        self.folder_add_share_button = toga.Button('Add share…', on_press=self.show_smb_connection,
                                                  style=Pack(height=TOUCH_TARGET, font_size=toga_font_size(CONTROL_TEXT), flex=1))
        toolbar_button(self.folder_add_share_button, 'plus')
        self.folder_add_remote_button = toga.Button('Add Remote…', on_press=self.show_cloud_connections,
                                                   style=Pack(height=TOUCH_TARGET, font_size=toga_font_size(CONTROL_TEXT), flex=1))
        toolbar_button(self.folder_add_remote_button, 'plus')
        self.folder_loading_status = toga.Label('', style=Pack(font_size=12, margin_bottom=4))
        self.folder_loading_progress = toga.ProgressBar(max=100, value=0, style=Pack(height=4, margin_bottom=8))
        backend = type(self.folder_add_share_button._impl).__module__
        if backend.startswith('toga_iOS.'):
            self.folder_add_share_button._impl.native.accessibilityLabel = 'Add SMB / Mac share'
        elif backend.startswith('toga_android.'):
            self.folder_add_share_button._impl.native.setContentDescription('Add SMB / Mac share')
        self.folder_credential_row = toga.Box(children=[surface(toga.Label('Credential',
                style=Pack(font_size=toga_font_size(CAPTION_TEXT), width=80, margin_right=12)),
                background='window', foreground='muted', outlined=False),
                self.folder_credential], style=Pack(direction=ROW, align_items=CENTER, margin_bottom=12))
        self.folder_picker_header = toga.Box(style=Pack(direction=COLUMN))
        self.folder_source_actions = toga.Box(style=Pack(direction=ROW))
        self.folder_loading_box = toga.Box(style=Pack(direction=COLUMN))
        incoming = getattr(self.app, 'incoming_status', '')
        self.app.incoming_notice = FittedLabel(incoming,
            style=Pack(display='pack' if incoming else 'none', font_size=12, margin_top=4))
        self.folder_source_tabs.style.flex = 1
        self.folder_source_tabs.style.margin_bottom = 0
        self.app._files_status_row = toga.Box(children=[self.folder_source_tabs],
            style=Pack(direction=ROW, align_items=CENTER, margin_bottom=12))
        box = toga.Box(children=[self.app._files_status_row, self.folder_local_header, self.folder_picker_header, self.folder_source_actions,
            self.folder_loading_box,
            folder_scroll(self.folder_list), self.app.incoming_notice],
            style=Pack(direction=COLUMN, margin=(8, 16, 12, 16), flex=1))
        self.update_folder_list(choices)
        host = self.app
        self.register_transfer_status(box, visible_when=lambda: host.folder_source == 'rclone'
            and (getattr(host, 'transfer_busy', False)
                 or (getattr(host, 'transfer_notification', False) and not getattr(host, 'transfer_complete', False))))
        self.folder_picker_view = box
        from .folder_hub_ui import reflow_folder_notice

        reflow_folder_notice(self.app)
        return box

    @batch_surfaces()
    def update_folder_list(self, choices):
        import json
        network_remotes = self.network_share_remotes()
        # Setup hints depend on configuration, not search/visibility filters or
        # the selected credential. Retained locked connections count too.
        associations = (json.loads(self.preferences.values['remote_packages'])
                        + self.retained_credential_associations()
                        + list(getattr(self, 'session_credential_packages', ())))
        loaded_remotes = set(self.loaded_remote_names())
        configured = set(loaded_remotes)
        configured.update(remote for item in associations for remote in item['remotes'])
        configured.update(remote for item in getattr(getattr(self, 'cloud_client', None), 'package_records', ())
                          for remote in item['remotes'])
        self.folder_configured_sources = set()
        if network_remotes:
            self.folder_configured_sources.add('Network shares')
        if configured - network_remotes:
            self.folder_configured_sources.add('rclone')
        credentials = self.credential_groups(source_choices(choices,
            'Local' if self.folder_source == 'Local' else 'rclone', network_remotes, local_group='Rclone'),
            loaded_remotes=loaded_remotes)
        if credentials != self.folder_credentials:
            self.folder_credentials = credentials
            selected = self.selected_folder_credential()
            self.folder_credential.on_change = None
            self.folder_credential.items = list(credentials)
            self.folder_credential.value = selected if selected in credentials else 'All'
            self.folder_credential_name = selected if selected in credentials else 'All'
            self.folder_credential.on_change = self.change_folder_credential
        self.folder_all_choices = choices
        self.folder_picker_choices = choices
        credential = self.selected_folder_credential()
        if type(self.folder_credential._impl).__module__.startswith('toga_android.'):
            # Android's native spinner supplies the arrow. Name the current
            # value explicitly because the content description labels the spinner.
            accessible_name(self.folder_credential, f'Credential filter: {credential}')
        selected = self.folder_credentials.get(credential)
        local_group = self.folder_local_group if self.folder_source == 'Local' else None
        visible = source_choices(choices, self.folder_source, network_remotes, local_group=local_group)
        if self.folder_source == 'Local':
            if not self.folder_local_header.children:
                self.folder_local_header.add(self.folder_local_tabs)
            if self.folder_local_styled != local_group:
                for group, button in self.folder_local_buttons.items():
                    source_tab(button, group == local_group)
                    accessible_name(button, group + (' selected' if group == local_group else ''))
                self.folder_local_styled = local_group
        elif self.folder_local_header.children:
            self.folder_local_header.remove(self.folder_local_tabs)
        credential_filter = self.folder_source == 'rclone' or local_group == 'Rclone'
        if credential_filter and selected is not None:
            visible = credential_choices(visible, selected)
        if self.folder_source_styled != self.folder_source:
            for source, button in self.folder_source_buttons.items():
                source_tab(button, source == self.folder_source)
                accessible_name(button, SOURCE_LABELS[source] + (' selected' if source == self.folder_source else ''))
            self.folder_source_styled = self.folder_source
        if credential_filter and not self.folder_picker_header.children:
            self.folder_picker_header.add(self.folder_credential_row)
        elif not credential_filter and self.folder_picker_header.children:
            self.folder_picker_header.remove(self.folder_credential_row)
        source_actions(self.app)
        visible = {name: entry for name, entry in visible.items()
                   if self.folder_path_visible(name) and self.folder_path_visible(entry.get('remote') or '')}
        self.folder_picker_choices = {**choices, **visible}
        # Native selectors and retained metadata are relatively expensive. Read
        # them once, rather than once for every encrypted folder in the tree.
        crypt_remotes = set(getattr(self.app, 'cloud_crypt_remotes', ()))
        crypt_remotes.update(remote for package in getattr(self.app.cloud_client, 'package_records', ())
                             for remote in package.get('crypt_identities', {}))
        crypt_remotes.update(remote for package in associations
                             for remote in package.get('crypt_remotes', ()))
        # Cache each source's native rows independently. Discovery/credential
        # metadata may change without changing anything this source displays.
        self._render_folder_tab(visible, loaded_remotes, crypt_remotes)

    def _build_folder_source_tabs(self):
        """Build source selectors with each callback bound to its own source."""
        self.folder_source_styled = None
        self.folder_source_buttons = {}
        self.folder_source_tabs = surface(toga.Box(
            style=Pack(direction=ROW, margin_bottom=12)),
            radius=11, background='alternate', outlined=False)
        for source in (('Local', 'rclone', 'Network shares') if self.app.feature_enabled('rclone') else ('Local',)):
            def select_source(widget=None, selected=source, **kwargs):
                if self.folder_source != selected:
                    self.change_folder_source(selected)
            button = toga.Button(SOURCE_LABELS[source], on_press=select_source,
                                 style=Pack(flex=1, height=TOUCH_TARGET,
                                            font_size=toga_font_size(CONTROL_TEXT), margin=2))
            backend = type(button._impl).__module__
            if backend.startswith('toga_iOS.'):
                button._impl.native.titleLabel.numberOfLines = 2
                button._impl.native.titleLabel.lineBreakMode = 0
                button._impl.native.titleLabel.textAlignment = 1
            elif backend.startswith('toga_android.'):
                # Share the row by label length and use the full touch height
                # for text. Material's default padding clips a second line at 48 dp.
                button.style.flex = 1.7 if source == 'Network shares' else 1
                pad = button._impl.scale_in(4)
                button._impl.native.setPaddingRelative(pad, 0, pad, 0)
                button._impl.native.setSingleLine(False)
                button._impl.native.setMaxLines(2)
            self.folder_source_buttons[source] = button
            self.folder_source_tabs.add(button)

    def _render_folder_tab(self, visible, loaded_remotes, crypt_remotes):
        """Project a filtered source into its retained native tree and mount it once."""
        key = (self.folder_source, self.folder_local_group if self.folder_source == 'Local' else None)
        tab = self.folder_tab_views.get(key)
        if tab is None:
            tab = FolderTreeView(
                browse=lambda name: self.browse_hub_folder(name),
                choose=lambda name: self.choose_folder(name),
                actions=lambda name: self.workspace_menu_actions(name),
                invoke=self.invoke_workspace_action,
                native_context=lambda: self.app._impl.native,
            )
            self.folder_tab_views[key] = tab
        tab.render(visible, self.folder_source, loaded_remotes, crypt_remotes,
                   grouped=not (self.folder_source == 'Local' and self.folder_local_group == 'Others'))
        self.folder_buttons, self.folder_tree_buttons = tab.buttons, tab.tree_buttons
        self.mount_folder_tab(tab.content)

    def mount_folder_tab(self, content):
        if list(self.folder_list.children) != [content]:
            for child in list(self.folder_list.children):
                self.folder_list.remove(child)
            self.folder_list.add(content)
