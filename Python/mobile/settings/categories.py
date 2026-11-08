"""Ordered Settings categories and their lazy page factories.

Substantial panels live in modules named for their visible Settings entry.
The owner methods remain the entry points for existing host integrations.
"""
from dataclasses import dataclass

import toga
from toga.style import Pack
from services.mobile_features import enabled

from .forms import page, SettingsLabel, switch_row, page_button
from .speech import speech_voice_setting


def display_title(app, title):
    if title == 'Books & Comics' and not enabled(app.preferences, 'comics'):
        from .reader_cover import available
        return 'Books & Comics' if enabled(app.preferences, 'books') and available(app) else 'PDF'
    return title


class SettingsCategories:
    def __init__(self, app):
        self.app = app

    def category(self, title):
        return page(title)


    def application(self):
        from .app import application
        return application(self.app)


    def appearance(self):
        from .appearance import appearance
        return appearance(self.app)

    def features(self):
        from ..feature_settings import feature_controls
        box = self.category('Features')
        feature_controls(self.app, box)
        if not enabled(self.app.preferences, 'notebooks'):
            return box
        preview = toga.Switch('Notebooks: muted Paper Pro colors',
            value=self.app.preferences.values['notebook_paper_preview'] == 'true',
            style=Pack(height=48))
        def changed(widget, **kw):
            self.app.preferences.save(notebook_paper_preview='true' if widget.value else 'false')

        def refresh():
            preview.on_change = None
            preview.value = self.app.preferences.values['notebook_paper_preview'] == 'true'
            preview.on_change = changed

        preview.on_change = changed
        box._settings_on_open = refresh
        box.add(switch_row(self.app, 'Notebook preview', preview,
            'Turn off for vivid colors. This setting applies to all notebooks, including PDF backgrounds and thumbnails.'))
        return box


    def speech(self):
        app = self.app
        box = self.category('Read aloud')
        voices = speech_voice_setting(app)
        box.add(voices)
        box._settings_on_open = voices._settings_on_open
        return box

    def privacy(self):
        from .privacy_security import privacy
        return privacy(self.app)


    def text_size(self, title, key):
        from .text import text_size
        return text_size(self.app, title, key)


    def epub(self):
        from .epub import epub
        return epub(self.app)


    def camera(self):
        app = self.app
        from features.images.mobile.burst_camera import settings_controls
        box = self.category('Camera')
        settings_controls(app, box)
        return box


    def books(self):
        app = self.app
        box = self.category(display_title(app, 'Books & Comics'))
        from ..magnifier import setting
        comics, pdf = (enabled(app.preferences, feature) for feature in ('comics', 'pdf'))
        if comics or pdf:
            reader = 'Comic & PDF' if comics and pdf else 'Comic' if comics else 'PDF'
            box.add(setting(app, reader + ' magnifier zoom'))
            box.add(SettingsLabel('While holding the magnifier, tap − or + to change its zoom.'))
        from .reader_cover import controls
        controls(app, box)
        return box


    def chat(self):
        app = self.app
        box = self.category('LM Chat')
        box.add(page_button('Server & generation settings…', on_press=lambda widget, **kw:
            app.show_chat_configuration(destination='settings'), style=Pack(height=48)))
        return box


    def workspaces(self):
        from .workspaces import workspaces
        return workspaces(self.app)


    def reset(self):
        app = self.app
        box = self.category('Reset')
        from .reader_history import controls as history_controls
        history_controls(app, box)
        box.add(page_button('Clear cached documents', on_press=app.show_saved_files,
                            style=Pack(height=48)))
        box.add(page_button('Erase all app data…', destructive=True, on_press=app.show_app_reset, style=Pack(height=48)))
        box.add(SettingsLabel('Delete private files, local app data, settings and metadata. Review the full scope before confirming.'))
        return box


    def help(self):
        from .help import help
        return help(self.app)

    def show_about(self, widget=None, **kwargs):
        from .help import show_about
        return show_about(self.app, widget, **kwargs)

    def about(self):
        from .help import about
        return about(self.app)


@dataclass(frozen=True)
class Category:
    """A menu entry; when listed, at least one required feature must be enabled."""
    title: str
    factory: str
    arguments: tuple = ()
    camera_required: bool = False
    icon: str = 'preferences'
    required_features: tuple[str, ...] = ()


CATEGORIES = (
    Category('App', 'application'),
    Category('Appearance', 'appearance', icon='appearance'),
    Category('Features', 'features'),
    Category('Camera', 'camera', camera_required=True, required_features=('images',)),
    Category('Read aloud', 'speech', icon='speaker'),
    Category('Markdown', 'text_size', ('Markdown', 'markdown_font_size'),
             icon='edit', required_features=('text_editor', 'notes_library')),
    Category('Text', 'text_size', ('Text', 'text_font_size'),
             icon='edit', required_features=('text_editor', 'notes_library')),
    Category('EPUB', 'epub', icon='books', required_features=('books',)),
    Category('Books & Comics', 'books', icon='books', required_features=('comics', 'pdf')),
    Category('LM Chat', 'chat', icon='chat', required_features=('lm',)),
    Category('Workspaces', 'workspaces', icon='folder'),
    Category('Privacy & Security', 'privacy', icon='storage_crypt'),
    Category('Reset', 'reset'),
    Category('Help', 'help', icon='help'),
    Category('About', 'about', icon='info'),
)
BY_TITLE = {entry.title: entry for entry in CATEGORIES}


def settings_sections(app):
    """Return ordered lazy factories; constructing the registry creates no pages."""
    from features.images.mobile.burst_camera import available
    app.settings_status = SettingsLabel(app.preferences.error, style=Pack(margin_top=12))
    owner = SettingsCategories(app)
    from .reader_cover import available as cover_available
    return {entry.title: lambda entry=entry: getattr(owner, entry.factory)(*entry.arguments)
            for entry in CATEGORIES if (not entry.camera_required or available(app))
            and (not entry.required_features or any(enabled(app.preferences, name)
                 for name in entry.required_features)
                 or (entry.factory == 'books' and enabled(app.preferences, 'books') and cover_available(app)))}
