"""Retain the native controls and layout for an admitted document picker."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from functools import partial
from pathlib import Path

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, NONE

from .control_icons import ICONS, button_icons, icon_button


class PickerMessage(toga.Box):
    """A message only occupies space when present; it is never a text field."""
    def __init__(self, width):
        from commonUtils.ui.native.forms import FittedLabel, fit_text
        self.label = FittedLabel('', style=Pack(font_size=14, margin_top=8))
        fit_text(self.label, max(120, width - 48))
        super().__init__(style=Pack(direction=COLUMN))

    @property
    def value(self):
        return self.label.text

    @value.setter
    def value(self, message):
        self.label.text = message
        if message and not self.children:
            self.add(self.label)
        elif not message and self.children:
            self.remove(self.label)


class DestinationForm:
    """Retained controls shared by the picker, native layout and keyboard hooks.

    The picker owns the operation and admits its callbacks. Keeping the form
    on that same instance preserves the native controls across layout changes.
    """

    def __init__(self):
        self.panel = None
        self.reset_creation_steps()
        self.creation_type = None
        self.notebook_templates = None

    def reset_creation_steps(self):
        self.creation_layout = None
        self.name_panel = self.location_panel = None

    def build_destination_form(self, roots, *, source_label, source_folder):
        """Attach the controls to the picker before it publishes the route."""
        operation = self.operation
        mode, name = operation.mode, operation.filename
        creation, destination_action = operation.creation, operation.destination_action
        name_label = 'Library folder name' if mode == 'folder' else 'File name'
        self.save_as_storage = toga.Selection(items=roots, style=Pack(height=48))
        self.picker_folder = toga.TextInput(placeholder='Folder within storage', style=Pack(height=48))
        if source_label is not None:
            self.save_as_storage.value = source_label
            self.picker_folder.value = source_folder
        self.picker_entries = toga.Selection(style=Pack(height=48))
        from .browser_ui import FileBrowser as NativeBrowser
        self.editor_browser = NativeBrowser(
            folder_visible=self.folder_path_visible, selected=self.browser_editor_selected,
            open_folder=self.browser_editor_folder, navigate=self.browser_editor_location,
            open_file=self.browser_editor_file, contextual_selection=False, preview=False)
        from .filename_input import FilenameInput
        directory = mode in ('open', 'folder') or getattr(destination_action, 'kind', '') in (
            'archive-create', 'archive-extract', 'archive-add')
        if getattr(destination_action, 'kind', '') in {'move', 'duplicate'}:
            directory = destination_action.provider.entry(destination_action.path)['directory']
        self.save_as_name = FilenameInput(value=name, directory=directory,
                                           placeholder=name_label, style=Pack(height=48))
        self.creation_type = None
        if creation is not None:
            self._build_creation_type(name)
        self.effective_name = self.editor_browser.status_label('')
        self.effective_name.style.flex = 0
        self.save_as_name.on_change = self.update_effective_name
        self.update_effective_name()
        self.save_as_status = PickerMessage(self.app.main_window.size.width)
        self.move_progress = toga.ProgressBar(max=None)
        self.move_notice = toga.Box(style=Pack(direction=COLUMN, margin_left=12, margin_right=12))
        title, primary = self._destination_labels()
        action = getattr(destination_action, 'kind', '')
        primary_icon = {'move': 'move_file', 'move-selection': 'move_file',
                        'duplicate': 'duplicate_file'}.get(action)
        self.picker_parent = icon_button('up', 'Parent folder', on_press=self.parent_editor_folder)
        self.picker_header = self.editor_browser.attach_location_header(
            self.editor_browser.status_label(''), self.picker_parent)
        if creation is not None:
            self.picker_parent.on_press = self.parent_editor_folder
        if creation is not None:
            from commonUtils.ui.native.forms import FittedLabel, fit_text
            self.picker_destination = FittedLabel('', style=Pack(font_size=13))
            fit_text(self.picker_destination, max(120, self.app.main_window.size.width - 48))
        else:
            self.picker_destination = self.editor_browser.status_label('')
        self.picker_destination.style.flex = 0
        from .appearance import action_button
        self.picker_primary = action_button(toga.Button(primary, on_press=self.confirm_editor_file, style=Pack(height=48, flex=1)))
        if primary_icon:
            button_icons(self.picker_primary, [(primary_icon, '')])
        self.picker_new_folder = button_icons(toga.Button(
            'New folder', on_press=self.toggle_editor_new_folder, style=Pack(height=48)), [('folder_add', '')])
        self.new_folder_name = toga.TextInput(placeholder='New folder name', style=Pack(height=48, flex=0 if creation is not None else 1))
        from .keyboard import prepare_picker_input
        for control in (self.save_as_name, self.new_folder_name):
            prepare_picker_input(control)
        folder_actions = toga.Box(children=[toga.Button('Create folder' if creation is not None else 'Create', on_press=self.create_picker_folder, style=Pack(height=48)),
            toga.Button('Cancel', on_press=self.hide_new_folder, style=Pack(height=48))], style=Pack(direction=ROW))
        self.new_folder_form = toga.Box(children=[self.new_folder_name, folder_actions], style=Pack(
            direction=COLUMN if creation is not None else ROW))
        name_fields = [toga.Label('Name' if destination_action is not None else name_label), self.save_as_name]
        if action == 'archive-add':
            name_fields[0].text = 'Select an item or enter its name'
        if action == 'archive-create':
            from .archive_operations import FORMATS
            self.archive_format = toga.Selection(items=list(FORMATS), style=Pack(height=48))
            name_fields += [self.archive_format]
        location_fields = [self.picker_destination, self.save_as_status]
        if action == 'move-selection':
            count = len(destination_action.entries)
            summary = self.editor_browser.status_label(f'{count} selected item' + ('s' if count != 1 else ''))
            summary.style.flex = 0
            location_fields.insert(0, summary)
        if creation is not None:
            self._build_creation_naming(operation, name_fields)
            self.save_as_view = toga.Box(children=location_fields,
                                        style=Pack(direction=COLUMN, margin_left=12, margin_right=12))
        else:
            fields = [] if action == 'move-selection' else [*name_fields, self.effective_name]
            self.save_as_view = toga.Box(children=[*fields, *location_fields],
                                        style=Pack(direction=COLUMN, margin=12))
        self.picker_actions = toga.Box(children=[
                toga.Button('Cancel', on_press=self.cancel_text_destination, style=Pack(height=48)),
                self.picker_primary],
                style=Pack(direction=ROW, margin_left=12, margin_right=12, margin_bottom=12))
        self.picker_form = toga.ScrollContainer(content=self.save_as_view, horizontal=False,
                                                style=Pack(height=80 if creation is not None or action == 'move-selection' else 180))
        # Keep the named action outside the compact location header: that
        # header reserves icon-sized slots and truncates "New folder" on phones.
        storage_row = self.save_as_storage
        if creation is not None and not type(self.save_as_storage._impl).__module__.startswith('toga_iOS.'):
            self.save_as_storage.style.flex = 1
            storage_row = toga.Box(children=[self.save_as_storage], style=Pack(direction=ROW))
        self._browse_controls = (storage_row, self.picker_header,
                                 self.picker_new_folder, self.editor_browser.scroll_container())
        if creation is not None:
            from .creation_layout import CreationLocation
            self.creation_location = CreationLocation(self)
            apple = type(self.save_as_storage._impl).__module__.startswith('toga_iOS.')
            self._browse_controls = (*(() if apple else (self.creation_location.heading,)),
                self.creation_location.storage, self.creation_location.header,
                self.editor_browser.scroll_container())
        contents = [*self._browse_controls, self.picker_form, self.picker_actions]
        panel = toga.Box(children=contents,
            style=Pack(direction=COLUMN, flex=1))
        from .ios_toolbar import prepare_form
        if creation is not None:
            self.location_panel = panel
            from .creation_layout import CreationLayout
            self.creation_layout = CreationLayout(self)
            self.listed_path = ''
        else:
            prepare_form(panel, primary=primary, cancel='Cancel',
                         primary_symbol=ICONS[primary_icon][0] if primary_icon else 'checkmark')
        self.panel = panel
        self._compact_keyboard = False
        self._naming_keyboard_active = False
        self.save_as_storage.on_change = self.change_editor_storage
        return panel, title

    def _destination_labels(self):
        action = self.operation.destination_action
        if self.operation.mode == 'folder':
            return 'New Notes Library', 'Create library here'
        if getattr(action, 'kind', '') == 'duplicate':
            return 'Duplicate', 'Duplicate here'
        if action is not None:
            return getattr(action, 'title', 'Move'), getattr(action, 'primary', 'Move here')
        if self.operation.creation is not None:
            return 'New document', 'Create here'
        if self.operation.mode == 'open':
            return 'Open file', 'Open file'
        return 'Save As', 'Save here'

    def _build_creation_type(self, name):
        from .document_choices import available_choices
        choices = self.creation_choices = available_choices(self.app)
        self.creation_type = toga.Selection(items=[label for label, _ in choices], style=Pack(height=48))
        suffix = Path(name).suffix.lower().removeprefix('.')
        if suffix == 'markdown':
            suffix = 'md'
        self.creation_type.value = next((label for label, extension in choices if extension == suffix), choices[0][0])
        self.creation_type.on_change = self.change_creation_type
        self.select_creation_format(self._creation_extension())

    def _build_creation_naming(self, operation, name_fields):
        from .creation_layout import CreationFormats, CreationNameForm
        self.save_as_name.on_confirm = self.choose_creation_location
        self.name_view = toga.Box(children=[*name_fields, self.effective_name],
                                  style=Pack(direction=COLUMN, margin=20))
        if any(extension == 'rmdoc' for _, extension in self.creation_choices):
            from features.notebooks.mobile.setup import NotebookTemplateChoices
            self.notebook_templates = NotebookTemplateChoices(partial(self.select_notebook_template, operation))
            self.sync_notebook_templates()
        self.creation_formats = CreationFormats(self)
        self.name_form = CreationNameForm(content=self.name_view, horizontal=False, style=Pack(flex=1))
        self.next_button = toga.Button('Next', on_press=self.choose_creation_location,
                                       style=Pack(height=48, flex=1), enabled=self._creation_name_valid)
        self.name_actions = toga.Box(children=[
            toga.Button('Cancel', on_press=self.cancel_text_destination, style=Pack(height=48)),
            self.next_button], style=Pack(direction=ROW, margin_left=12, margin_right=12, margin_bottom=12))
        self.name_content = toga.Box(children=[self.name_form], style=Pack(direction=COLUMN, flex=1))
        self.creation_formats.fit(False, 0, self.app.main_window.size.width)
        self.name_panel = toga.Box(children=[self.name_content, self.name_actions], style=Pack(direction=COLUMN, flex=1))

    def clear_destination_fields(self):
        """Scrub displayed private values before the picker drops its source."""
        if hasattr(self, 'editor_browser'):
            self.editor_browser.stop()
        if hasattr(self, 'creation_location'):
            self.creation_location.crumbs.clear()
        if hasattr(self, 'picker_destination'):
            self.picker_destination.text = ''
            self.picker_header.folder_name.text = ''
            self.picker_header.status.value = ''
        if hasattr(self, 'picker_entries'):
            self.picker_entries.items = []
            self.picker_folder.value = ''
            self.save_as_name.value = ''
            self.new_folder_name.value = ''
            self.save_as_storage.items = []
            self.save_as_status.value = ''

        self.discard_notebook_templates()

    def discard_notebook_templates(self):
        if self.notebook_templates is not None:
            self.notebook_templates.set_preview_active(False)
            self.notebook_templates.changed = lambda *args: None
            self.notebook_templates = None

    def show_naming_step(self):
        self.hide_new_folder()
        self.fit_keyboard(False)
        self.panel = self.name_panel
        self.next_button.enabled = self._creation_name_valid
        self.creation_layout.reflow()

    def show_location_step(self):
        from .keyboard import dismiss_picker_keyboard
        self.fit_keyboard(False)
        self.panel = self.location_panel
        dismiss_picker_keyboard(self)
        self.creation_layout.reflow()

    def fit_keyboard(self, compact):
        """Keep naming and completion usable without reparenting the focused input."""
        if self.panel is None or not hasattr(self, 'picker_form') or getattr(self, '_fitting_keyboard', False):
            return
        from .keyboard import _tuck_control, reset_picker_keyboard
        self._fitting_keyboard = True
        try:
            self._compact_keyboard = compact
            apple = type(self.app._impl).__module__.startswith('toga_iOS.')
            if apple and not compact:
                reset_picker_keyboard(self)
            def focused(control):
                return bool(getattr(getattr(control._impl, 'native', None), 'isFirstResponder', False))
            if not compact or not apple or focused(self.save_as_storage):
                self._naming_keyboard_active = False
            elif focused(self.save_as_name) or focused(self.new_folder_name):
                self._naming_keyboard_active = True
            naming = self.panel is self.name_panel
            paired = self.creation_layout is not None and self.creation_layout.paired
            controls = () if naming else self._browse_controls
            editing_folder = self.entering_creation_folder()
            hide_browser = editing_folder or (compact and not paired)
            if not hide_browser:
                controls = reversed(controls)
            for control in controls:
                # iOS Selection opens a keyboard inputView. Removing its text
                # field here immediately resigns focus and closes that picker.
                # A location read briefly disables the field and drops focus;
                # preserve its input-view session until typing or keyboard hide.
                preserve_selector = ((control is self.save_as_storage or
                    (self.creation_type is not None and control is self.creation_location.storage)) and apple
                    and not self._naming_keyboard_active)
                _tuck_control(control, hide_browser and (editing_folder or not preserve_selector))
            # A landscape keyboard can leave only ~100 logical pixels.
            # Put full-size completion buttons beside the scrollable form;
            # stacking both areas would squash the native buttons to a sliver.
            visible_height = self.app.main_window.size.height
            # UIKit keeps the outer window size and reserves the keyboard in
            # safe-area insets. Android already reports its resized viewport.
            if compact and apple:
                visible_height -= self.app.native_host.adapter.keyboard_inset
            if self.creation_type is not None:
                width = (self.name_panel.style.width if paired else
                         self.app.adaptive.content_width(self.app.native_host.state.destination, margin=0))
                # UIKit location selections also present a keyboard inputView.
                # Only collapse formats for text entry, not location browsing;
                # retain the naming-session flag across transient focus loss.
                format_keyboard = compact and (not apple or self._naming_keyboard_active)
                self.creation_formats.fit(format_keyboard, visible_height - 120, width)
            # Creation's UIKit completion lives in its native navigation bar.
            # Other picker forms retain their existing short-viewport layout.
            tight = (compact and not paired and visible_height < 220
                     and (not apple or self.creation_type is None))
            actions = self.name_actions if naming else self.picker_actions
            changes = ((self.panel, 'direction', ROW if tight else COLUMN),
                       (actions, 'direction', COLUMN if tight else ROW),
                       (actions, 'width', 112 if tight else NONE),
                       (actions, 'margin_bottom', 0 if tight else 12))
            for control, field, value in changes:
                if getattr(control.style, field) != value:
                    setattr(control.style, field, value)
            expand_form = naming or editing_folder or (compact and not paired)
            flex = 1 if expand_form else 0
            form = self.name_form if naming else self.picker_form
            if form.style.flex != flex:
                form.style.flex = flex
            # Travertino layout sizes already use logical units. Scaling them
            # out again clips the status area on high-density Android screens.
            natural = self.save_as_view.layout.min_height or 180
            minimum = 72 if self.location_panel is not None else 120
            height = NONE if expand_form else min(max(minimum, natural), max(minimum, self.app.main_window.size.height / 2))
            if form.style.height != height:
                form.style.height = height
        finally:
            self._fitting_keyboard = False
        if not compact and apple:
            from .keyboard import reset_picker_keyboard_insets
            reset_picker_keyboard_insets(self)
        pending = getattr(self, '_keyboard_reveal', None)
        if pending is not None:
            pending.cancel()
            self._keyboard_reveal = None
        if compact and apple:
            # UIKit and Toga resize the scroll viewport after the keyboard/rotation
            # callback. Reveal the existing first responder in that final layout.
            panel = self.panel
            def reveal():
                self._keyboard_reveal = None
                if self.panel is panel and self._compact_keyboard and self.active_host and self.visible():
                    from .keyboard import reveal_picker_input
                    reveal_picker_input(self)
            self._keyboard_reveal = self.app.loop.call_soon(reveal)

    def update_effective_name(self, widget=None, **kwargs):
        if self.operation.mode != 'save':
            self.effective_name.text = ''
            return
        try:
            self.effective_name.text = 'Save as: ' + self.destination_filename()
            self._creation_name_valid = True
        except ValueError as error:
            self._creation_name_valid = False
            self.effective_name.text = str(error) if self.save_as_name.value else 'Enter a file name.'
        if self.name_panel is not None:
            self.next_button.enabled = self._creation_name_valid
            if self.listed_path:
                self.update_creation_summary()
        if self.operation.creation is not None and self.save_as_name.parent is not None and self.visible():
            self.update_picker_actions()

    def update_creation_summary(self):
        name = self.destination_filename() if self._creation_name_valid else 'Enter a valid file name'
        self.picker_destination.text = f'{name}\nIn {self.listed_path}'

    def destination_filename(self):
        if self.operation.creation is not None:
            from .document_choices import creation_filename
            return creation_filename(self.save_as_name.value, self._creation_extension())
        from .destination_names import save_filename
        return save_filename(self.save_as_name.value, self.operation.filename, extensions=self.picker_extensions())

    def _creation_extension(self):
        return dict(self.creation_choices)[self.creation_type.value]

    def change_creation_type(self, widget=None, **kwargs):
        extension = self._creation_extension()
        self.select_creation_format(extension)
        self.save_as_name.set_extension('.' + extension)
        self.creation_formats.update()
        self.sync_notebook_templates()
        self.update_effective_name()

    def sync_notebook_templates(self):
        controls = self.notebook_templates
        if controls is None:
            return
        enabled = self._creation_extension() == 'rmdoc'
        if enabled and controls.parent is None:
            self.name_view.add(controls)
            controls.set_preview_active(True)
        elif not enabled and controls.parent is self.name_view:
            controls.set_preview_active(False)
            self.name_view.remove(controls)

    def present_picker_location(self, label, folder, *, has_parent, private, suggest_creation):
        if self.creation is not None:
            from .control_icons import apply_icon
            apply_icon(self.picker_parent, 'up', 'Parent folder')
        self.picker_parent.enabled = has_parent
        privacy = 'Encrypted' if private else 'Plaintext'
        if self.creation is not None:
            self.creation_location.update(label, folder)
            self.listed_path = ' › '.join([label, *filter(None, folder.split('/'))]) + f' · {privacy}'
            self.update_creation_summary()
        else:
            self.picker_destination.text = f'{label} / {folder or "Root"} · {privacy}'
        self.save_as_status.value = 'Create a folder, or save here.' if suggest_creation else ''

    def disable_picker_actions(self):
        self.save_as_storage.enabled = False
        self.picker_parent.enabled = False
        self.picker_primary.enabled = False
        if self.location_panel is not None:
            self.edit_name.enabled = False
            self.creation_location.set_enabled(False)
            self.creation_type.enabled = self.save_as_name.enabled = False
            self.creation_formats.set_enabled(False)
        self.picker_new_folder.enabled = False

    def present_picker_actions(self, *, ready, has_parent, busy, working,
                               can_create_folder, can_submit, virtual_root):
        self.save_as_storage.enabled = not busy
        self.save_as_name.enabled = not working
        if self.creation_type is not None:
            self.creation_type.enabled = not working
            self.creation_formats.set_enabled(not working)
        self.picker_parent.enabled = has_parent
        if self.location_panel is not None:
            self.edit_name.enabled = not busy
            self.creation_location.set_enabled(ready and not self.entering_creation_folder())
        self.picker_new_folder.enabled = can_create_folder
        if self.operation.mode == 'folder':
            can_submit = can_submit and not self.entering_creation_folder()
        elif self.operation.mode != 'open' and self.creation is not None:
            can_submit = can_submit and self._creation_name_valid and not self.entering_creation_folder()
        self.picker_primary.enabled = can_submit
        if self.operation.mode not in ('open', 'folder'):
            self.picker_primary.text = ('Choose a folder first' if virtual_root and self.creation is None else
                                        self._destination_labels()[1])
            if virtual_root:
                self.save_as_status.value = ('Open a folder to create your document here.'
                    if self.operation.creation is not None else
                    'Choose Local or Received Files above, then choose or create a folder.')
        self.fit_keyboard(getattr(self, '_compact_keyboard', False))

    def entering_creation_folder(self):
        return ((self.creation is not None or self.operation.mode == 'folder')
                and self.new_folder_form in self.save_as_view.children)

    def show_new_folder(self, widget=None, **kwargs):
        if not self.picker_new_folder.enabled:
            return
        if self.creation is not None:
            self.panel = self.location_panel
            self.creation_layout.reflow()
        self.new_folder_name.value = ''
        if self.new_folder_form not in self.save_as_view.children:
            self.save_as_view.insert(1, self.new_folder_form)
        if self.entering_creation_folder():
            self.update_picker_actions()
        self.new_folder_name.focus()

    def hide_new_folder(self, widget=None, **kwargs):
        if hasattr(self, 'new_folder_form') and self.new_folder_form in self.save_as_view.children:
            entering_folder = self.entering_creation_folder()
            if entering_folder:
                if self._work is not None:
                    return
                from .keyboard import dismiss_picker_keyboard
                dismiss_picker_keyboard(self, self.new_folder_name)
            self.save_as_view.remove(self.new_folder_form)
            if entering_folder:
                if self.save_as_status.value.startswith('Folder creation failed:'):
                    self.save_as_status.value = ''
                self.update_picker_actions()

    def toggle_editor_new_folder(self, widget=None, **kwargs):
        if self.new_folder_form in self.save_as_view.children:
            self.hide_new_folder()
        else:
            self.show_new_folder()
