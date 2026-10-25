"""Shared new-document form for every mobile entry point."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from features.text_editor.names import document_name

CHOICES = (('Plain text (.txt)', 'txt'), ('Markdown (.md)', 'md'))


def choose_document_type(app):
    destination = app.native_host.state.destination
    origin = (destination, len(app.routes.screens[destination]), len(app.adaptive.detail_routes))
    box = toga.Box(style=Pack(direction=COLUMN, margin=16))
    name = toga.TextInput(placeholder='File name', style=Pack(height=48))
    error = toga.Label('', style=Pack(margin_top=8))
    kind = toga.Selection(items=[label for label, extension in CHOICES],
                          style=Pack(height=48))

    async def create(widget, **kwargs):
        if not app.active_host:
            return
        extension = dict(CHOICES)[kind.value]
        try:
            filename = document_name(name.value)
            # Selecting a type controls the extension; accept either a base
            # name or the full filename without doubling a matching suffix.
            suffixes = ('.md', '.markdown') if extension == 'md' else ('.txt',)
            if not filename.lower().endswith(suffixes):
                filename = document_name(filename + '.' + extension)
        except ValueError as exc:
            error.text = str(exc)
            return
        await app.editor_picker().show_document_creation(filename, origin)

    box.name_input, box.type_selector, box.error_label = name, kind, error
    box.create_button = toga.Button('Choose location…', on_press=create, style=Pack(height=48))
    box.cancel_button = toga.Button('Cancel', on_press=lambda widget, **kw: app.routes.back(),
                                    style=Pack(height=48))
    box.add(toga.Label('File name'), name, toga.Label('File type'), kind, error,
            box.create_button, box.cancel_button)
    app.show_view(toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1)),
                  route='new-document', title='New document')
    name.focus()
