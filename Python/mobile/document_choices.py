"""Shared new-document entry point and format choices for mobile."""
from pathlib import PurePosixPath

CHOICES = (('Plain text (.txt)', 'txt'), ('Markdown (.md)', 'md'), ('Remarkable Document (.rmdoc)', 'rmdoc'))


def available_choices(app):
    from services.mobile_features import enabled
    return tuple((label, extension) for label, extension in CHOICES
        if enabled(app.preferences, 'notebooks' if extension == 'rmdoc' else 'text_editor'))


def creation_filename(name, extension):
    """Validate the visible name against the explicitly selected format."""
    from services.documents.names import document_name
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
    choices = available_choices(app)
    if not choices:
        app.require_feature('text_editor')
        return
    destination = app.native_host.state.destination
    origin = (destination, len(app.routes.screens[destination]), len(app.adaptive.detail_routes))
    body = app.body
    async def choose():
        # Initial credential restoration owns the provider's busy flag before
        # Home is interactive. Retain a New request until that startup work
        # releases the picker instead of silently dropping the first tap.
        import asyncio
        for name in ('cloud_startup_task', 'cloud_restore_task'):
            pending = getattr(app, name, None)
            if app.cloud_busy and pending is not None and not pending.done():
                await asyncio.shield(pending)
        if (app.active_host and app.body is body
                and app.native_host.state.destination == destination):
            # Format belongs to the retained naming form, not a preceding alert.
            await app.editor_picker().show_document_creation('Untitled.' + choices[0][1], origin)
    return app.loop.create_task(choose())
