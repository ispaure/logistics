"""Shared new-document form for every mobile entry point."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from features.text_editor.names import document_name

CHOICES = (('Plain text (.txt)', 'txt'), ('Markdown (.md)', 'md'))


def choose_document_type(app):
    box = toga.Box(style=Pack(direction=COLUMN, margin=16))
    name = toga.TextInput(placeholder='Document name', style=Pack(height=48))
    title = toga.TextInput(placeholder='Optional title', style=Pack(height=48))
    title_label = toga.Label('Title (optional)')
    error = toga.Label('', style=Pack(margin_top=8))

    def type_changed(widget, **kwargs):
        markdown = widget.value == CHOICES[1][0]
        title.enabled = markdown
        title_label.text = 'Title (optional)' if markdown else 'Title (Markdown only)'

    kind = toga.Selection(items=[label for label, extension in CHOICES],
                          on_change=type_changed, style=Pack(height=48))
    type_changed(kind)

    def create(widget, **kwargs):
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
            heading = title.value.strip() if extension == 'md' else ''
            if '\n' in heading or '\r' in heading:
                raise ValueError('Use a single line for the title.')
        except ValueError as exc:
            error.text = str(exc)
            return
        if not app.create_chosen_document(extension, name=filename,
                                          content=('# ' + heading + '\n\n') if heading else ''):
            error.text = app.status.text

    box.add(toga.Label('Document name'), name, toga.Label('File type'), kind,
            title_label, title, error,
            toga.Button('Create document', on_press=create, style=Pack(height=48)),
            toga.Button('Cancel', on_press=lambda widget, **kw: app.routes.back(), style=Pack(height=48)))
    app.show_view(toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1)),
                  destination='documents', route='new-document', title='New document')
    name.focus()
