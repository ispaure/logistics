"""Build the native destination form for an admitted document picker."""
from pathlib import Path

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from .control_icons import icon_button


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


def build_destination_form(picker, *, source_label, source_folder):
    """Attach the controls to the picker before it publishes the route."""
    operation = picker.operation
    mode, name = operation.mode, operation.filename
    creation, destination_action = operation.creation, operation.destination_action
    roots = list(picker.editor_storage_roots)
    picker.editor_picker_rows = {}
    picker.save_as_storage = toga.Selection(items=roots, style=Pack(height=48))
    picker.picker_folder = toga.TextInput(placeholder='Folder within storage', style=Pack(height=48))
    if source_label is not None:
        picker.save_as_storage.value = source_label
        picker.picker_folder.value = source_folder
    picker.picker_entries = toga.Selection(style=Pack(height=48))
    from .browser_ui import FileBrowser as NativeBrowser
    picker.editor_browser = NativeBrowser(folder_visible=picker.folder_path_visible, selected=picker.browser_editor_selected, open_folder=picker.browser_editor_folder, navigate=picker.browser_editor_location, open_file=picker.browser_editor_file, contextual_selection=False, preview=False)
    from .filename_input import FilenameInput
    directory = mode == 'open'
    if getattr(destination_action, 'kind', '') == 'move':
        directory = destination_action.provider.entry(destination_action.path)['directory']
    picker.save_as_name = FilenameInput(value=name, directory=directory,
                                       placeholder='File name', style=Pack(height=48))
    picker.creation_type = None
    if creation is not None:
        from .document_choices import available_choices
        choices = picker.creation_choices = available_choices(picker.app)
        picker.creation_type = toga.Selection(items=[label for label, extension in choices],
                                             style=Pack(height=48))
        suffix = Path(name).suffix.lower().removeprefix('.')
        picker.creation_type.value = next((label for label, extension in choices
            if extension == ('md' if suffix == 'markdown' else suffix)), choices[0][0])
        picker.creation_type.on_change = picker.change_creation_type
        picker.operation.filename = 'Untitled.' + dict(choices)[picker.creation_type.value]
    picker.effective_name = picker.editor_browser.status_label('')
    picker.effective_name.style.flex = 0
    picker.save_as_name.on_change = picker.update_effective_name
    picker.update_effective_name()
    picker.save_as_status = PickerMessage(picker.app.main_window.size.width)
    picker.move_progress = toga.ProgressBar(max=None)
    picker.move_notice = toga.Box(style=Pack(direction=COLUMN, margin_left=12, margin_right=12))
    title = getattr(destination_action, 'title', 'Move') if destination_action is not None else 'New document' if creation is not None else 'Open file' if mode == 'open' else 'Save As'
    primary = getattr(destination_action, 'primary', 'Move here') if destination_action is not None else 'Create here' if creation is not None else 'Open file' if mode == 'open' else 'Save here'
    picker.picker_parent = icon_button('up', 'Parent folder', on_press=picker.parent_editor_folder)
    picker.picker_header = picker.editor_browser.attach_location_header(
        picker.editor_browser.status_label(''), picker.picker_parent)
    if creation is not None:
        picker.picker_parent.on_press = picker.parent_editor_folder
    if creation is not None:
        from commonUtils.ui.native.forms import FittedLabel, fit_text
        picker.picker_destination = FittedLabel('', style=Pack(font_size=13))
        fit_text(picker.picker_destination, max(120, picker.app.main_window.size.width - 48))
    else:
        picker.picker_destination = picker.editor_browser.status_label('')
    picker.picker_destination.style.flex = 0
    from .appearance import action_button
    picker.picker_primary = action_button(toga.Button(primary, on_press=picker.confirm_editor_file, style=Pack(height=48, flex=1)))
    picker.picker_new_folder = toga.Button('New folder', on_press=picker.toggle_editor_new_folder, style=Pack(height=48))
    picker.new_folder_name = toga.TextInput(placeholder='New folder name', style=Pack(height=48, flex=0 if creation is not None else 1))
    from .keyboard import prepare_picker_input
    for control in (picker.save_as_name, picker.new_folder_name):
        prepare_picker_input(control)
    folder_actions = toga.Box(children=[toga.Button('Create folder' if creation is not None else 'Create', on_press=picker.create_picker_folder, style=Pack(height=48)),
        toga.Button('Cancel', on_press=picker.hide_new_folder, style=Pack(height=48))], style=Pack(direction=ROW))
    picker.new_folder_form = toga.Box(children=[picker.new_folder_name, folder_actions], style=Pack(
        direction=COLUMN if creation is not None else ROW))
    name_fields = [toga.Label('Name' if destination_action is not None else 'File name'), picker.save_as_name]
    location_fields = [picker.picker_destination, picker.save_as_status]
    if creation is not None:
        picker.save_as_name.on_confirm = picker.choose_creation_location
        picker.name_view = toga.Box(children=[*name_fields, picker.effective_name],
            style=Pack(direction=COLUMN, margin=20))
        from .creation_layout import CreationFormats, CreationNameForm
        if any(extension == 'rmdoc' for _, extension in picker.creation_choices):
            from features.notebooks.mobile.setup import NotebookTemplateChoices
            def selected(template, paper_format):
                if picker.operation is operation and picker._work is None:
                    operation.notebook_template, operation.notebook_format = template, paper_format
            picker.notebook_templates = NotebookTemplateChoices(selected)
            picker.sync_notebook_templates()
        picker.creation_formats = CreationFormats(picker)
        picker.name_form = CreationNameForm(content=picker.name_view, horizontal=False, style=Pack(flex=1))
        picker.next_button = toga.Button('Next', on_press=picker.choose_creation_location,
                                       style=Pack(height=48, flex=1), enabled=picker._creation_name_valid)
        picker.name_actions = toga.Box(children=[
            toga.Button('Cancel', on_press=picker.cancel_text_destination, style=Pack(height=48)),
            picker.next_button], style=Pack(direction=ROW, margin_left=12, margin_right=12, margin_bottom=12))
        picker.name_content = toga.Box(children=[picker.name_form], style=Pack(direction=COLUMN, flex=1))
        picker.creation_formats.fit(False, 0, picker.app.main_window.size.width)
        picker.name_panel = toga.Box(children=[picker.name_content, picker.name_actions], style=Pack(direction=COLUMN, flex=1))
        picker.save_as_view = toga.Box(children=location_fields,
                                    style=Pack(direction=COLUMN, margin_left=12, margin_right=12))
    else:
        picker.save_as_view = toga.Box(children=[*name_fields, picker.effective_name, *location_fields],
                                    style=Pack(direction=COLUMN, margin=12))
    picker.picker_actions = toga.Box(children=[
            toga.Button('Cancel', on_press=picker.cancel_text_destination, style=Pack(height=48)),
            picker.picker_primary],
            style=Pack(direction=ROW, margin_left=12, margin_right=12, margin_bottom=12))
    picker.picker_form = toga.ScrollContainer(content=picker.save_as_view, horizontal=False,
                                            style=Pack(height=80 if creation is not None else 180))
    # Keep the named action outside the compact location header: that
    # header reserves icon-sized slots and truncates "New folder" on phones.
    storage_row = picker.save_as_storage
    if creation is not None and not type(picker.save_as_storage._impl).__module__.startswith('toga_iOS.'):
        picker.save_as_storage.style.flex = 1
        storage_row = toga.Box(children=[picker.save_as_storage], style=Pack(direction=ROW))
    picker._browse_controls = (storage_row, picker.picker_header,
                             picker.picker_new_folder, picker.editor_browser.scroll_container())
    if creation is not None:
        from .creation_layout import CreationLocation
        picker.creation_location = CreationLocation(picker)
        apple = type(picker.save_as_storage._impl).__module__.startswith('toga_iOS.')
        picker._browse_controls = (*(() if apple else (picker.creation_location.heading,)),
            picker.creation_location.storage, picker.creation_location.header,
            picker.editor_browser.scroll_container())
    contents = [*picker._browse_controls, picker.picker_form, picker.picker_actions]
    panel = toga.Box(children=contents,
        style=Pack(direction=COLUMN, flex=1))
    from .ios_toolbar import prepare_form
    if creation is not None:
        picker.location_panel = panel
        from .creation_layout import CreationLayout
        picker.creation_layout = CreationLayout(picker)
        picker.listed_path = ''
    else:
        prepare_form(panel, primary=primary, cancel='Cancel')
    picker.panel = panel
    picker._compact_keyboard = False
    picker._naming_keyboard_active = False
    picker.save_as_storage.on_change = picker.change_editor_storage
    return panel, title
