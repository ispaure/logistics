"""Shared new-document entry point and format choices for mobile."""
from pathlib import PurePosixPath

CHOICES = (('Plain text (.txt)', 'txt'), ('Markdown (.md)', 'md'), ('Notebook (.rmdoc)', 'rmdoc'))


def available_choices(app):
    from services.mobile_features import enabled
    return tuple((label, extension) for label, extension in CHOICES
        if enabled(app.preferences, 'notebooks' if extension == 'rmdoc' else 'text_editor'))


def creation_filename(name, extension):
    """Validate the visible name against the explicitly selected format."""
    from features.text_editor.names import document_name
    from .destination_names import save_filename
    extensions = ('.md', '.markdown') if extension == 'md' else ('.' + extension,)
    return document_name(save_filename(name, 'Untitled.' + extension, extensions=extensions))


def change_creation_suffix(name, extension):
    """Replace a known document suffix when switching formats; keep base names."""
    suffix = PurePosixPath(name).suffix
    if suffix.lower() in ('.txt', '.md', '.markdown', '.rmdoc'):
        if extension == 'md' and suffix.lower() in ('.md', '.markdown'):
            return name
        return name[:-len(suffix)] + '.' + extension
    return name


def choose_document_type(app):
    if not available_choices(app):
        app.require_feature('text_editor')
        return
    destination = app.native_host.state.destination
    origin = (destination, len(app.routes.screens[destination]), len(app.adaptive.detail_routes))
    return app.loop.create_task(app.editor_picker().show_document_creation('', origin))
