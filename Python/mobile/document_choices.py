"""Shared new-document entry point and format choices for mobile."""
from pathlib import PurePosixPath

CHOICES = (('Plain text (.txt)', 'txt'), ('Markdown (.md)', 'md'), ('Remarkable Document (.rmdoc)', 'rmdoc'))


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
    generation = app.navigation_generation
    async def choose():
        from features.text_editor.mobile.document_dialogs import DocumentTypeDialog
        icons = {'txt': '≡  Plain text', 'md': 'Ⓜ  Markdown', 'rmdoc': '▧  Remarkable Document'}
        choices = [(icons[ext], ext) for _, ext in available_choices(app)]
        extension = await app.main_window.dialog(DocumentTypeDialog(choices=choices))
        if (app.active_host and app.navigation_generation == generation
                and extension in {ext for _, ext in available_choices(app)}):
            await app.editor_picker().show_document_creation('Untitled.' + extension, origin)
    return app.loop.create_task(choose())
