"""Compact preference rows and offline installed-build information."""
import json
from pathlib import Path
import sys
from collections.abc import Mapping

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from services.build_version import BuildVersion, installed_build


from commonUtils.ui.native import forms as _forms
from commonUtils.ui.native.forms import wrap_text


from dataclasses import dataclass
from .forms import SettingsLabel, switch_row
from .information import build_information
from .speech import speech_voice_setting


class SettingsCategories:
    def __init__(self, app):
        self.app = app

    def category(self, title):
        from ..hub_ui import heading
        app = self.app
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(heading(title))
        return box


    def application(self):
        app = self.app
        box = self.category('App')
        app.restore_choice = toga.Switch('Restore last document',
            value=app.preferences.values['restore_last_document'] == 'true', style=Pack(height=48))
        app.clear_documents_choice = toga.Switch('Clear on restart',
            value=app.preferences.values['clear_unmodified_documents_on_restart'] == 'true',
            style=Pack(height=48))
        box.add(switch_row(app, 'Restore last document', app.restore_choice,
            'Resume the last active document when the app starts, including ordinary EPUB and comic readers. '
            'Session-only documents, including those loaded using session-only credentials, are never restored.'))
        box.add(switch_row(app, 'Close saved documents on restart', app.clear_documents_choice,
            'Closes documents with no pending changes in Open documents when the app restarts. '
            'The last active document is kept when Restore last document is on. '
            'Stored documents, reading progress and unsaved drafts are kept.'))
        box.add(toga.Label('Preferences save automatically on this device.', style=Pack(font_size=12)))
        box.add(toga.Button('Reload preferences', on_press=app.reload_preferences, style=Pack(height=48)))
        if app.scene_manager.supported:
            box.add(toga.Button('New window', on_press=app.scene_manager.new_window, style=Pack(height=48)))
            if app.window_id != 'primary':
                box.add(toga.Button('Close window', on_press=lambda widget, **kw:
                    app.scene_manager.close_window(app), style=Pack(height=48)))
        app.restore_choice.on_change = app.save_preferences
        app.clear_documents_choice.on_change = app.save_preferences
        return box


    def appearance(self):
        app = self.app
        box = self.category('Appearance')
        app.snow_choice = toga.Switch('Seasonal snow',
            value=app.preferences.values['seasonal_snow'] == 'true', style=Pack(height=48))
        box.add(switch_row(app, 'Seasonal snow', app.snow_choice,
            'Snow from December 15 through January 2, inclusive. On by default. '
            'Disabled in high-contrast / E Ink mode. Saved immediately.'))
        app.snow_choice.on_change = app.change_seasonal_snow
        if not type(app._impl).__module__.startswith('toga_android.'):
            return box
        app.android_eink_choice = toga.Switch('High contrast / E Ink',
            value=app.preferences.values['android_eink'] == 'true', style=Pack(height=48))
        box.add(switch_row(app, 'High contrast / E Ink', app.android_eink_choice,
            'Use black text on white, strong borders and simpler controls. Overrides dark mode and reader colors '
            'without changing images or files. Saved immediately. No BOOX hardware refresh control.'))
        app.android_eink_choice.on_change = app.change_android_eink
        return box

    def features(self):
        from ..feature_settings import feature_controls
        box = self.category('Features')
        feature_controls(self.app, box)
        return box


    def speech(self):
        app = self.app
        box = self.category('Read aloud')
        box.add(speech_voice_setting(app))
        app.session_speech_choice = toga.Switch('Session-only speech while locked',
            value=app.preferences.values['session_speech_when_locked'] == 'true',
            on_change=app.change_session_speech, style=Pack(height=48))
        box.add(switch_row(app, 'Session-only speech while locked', app.session_speech_choice,
            'Allow already-started read-aloud from session-only credentials to keep playing '
            'and show system playback controls while locked. Off by default. This choice is saved. '
            'It does not unlock credentials or permit new file reads while locked.'))
        return box


    def text_size(self, title, key):
        app = self.app
        box = self.category(title)
        box.add(toga.Label(title + ' font size'))
        choice = toga.Selection(items=[str(size) for size in range(12, 33)],
            value=app.preferences.values[key], style=Pack(height=48))
        setattr(app, key + '_choice', choice)
        choice.on_change = app.save_preferences
        box.add(choice)
        box.add(toga.Label('Pinch to adjust. Saved for this format on this device.', style=Pack(font_size=12)))
        if title in {'Markdown', 'EPUB'}:
            justify_key = title.lower() + '_justify'
            justify = toga.Switch('Justify text', value=app.preferences.values[justify_key] == 'true', style=Pack(height=48))
            setattr(app, justify_key + '_choice', justify)
            box.add(switch_row(app, 'Justify text', justify,
                'Align paragraphs and lists to both edges. Saved for this format on this device.'))
            justify.on_change = app.save_preferences
        return box


    def audio(self):
        from .audio import controls
        box = self.category('Audio playback')
        controls(self.app, box)
        return box

    def camera(self):
        app = self.app
        from features.images.mobile.burst_camera import settings_controls
        box = self.category('Camera')
        settings_controls(app, box)
        return box


    def books(self):
        app = self.app
        box = self.category('Books & Comics')
        from ..magnifier import setting
        box.add(toga.Label('Comic & PDF magnifier zoom'))
        app.magnifier_choice = setting(app)
        box.add(app.magnifier_choice)
        box.add(toga.Label('Keep holding; tap −/+ just outside the lens’s upper corners.\nShared across comics and PDFs. Saved immediately.', style=Pack(font_size=12)))
        box.add(toga.Button('Saved books & comics…', on_press=app.show_saved_files, style=Pack(height=48)))
        box.add(toga.Label('Use Appearance in an open reader\nto adjust its pages.', style=Pack(font_size=12)))
        return box


    def chat(self):
        app = self.app
        box = self.category('LM Chat')
        box.add(toga.Button('Server & generation settings…', on_press=app.show_chat_configuration, style=Pack(height=48)))
        return box


    def workspaces(self):
        app = self.app
        box = self.category('Workspaces')
        if type(app._impl).__module__.startswith('toga_android.'):
            box.add(toga.Button('Local / LocalCrypt location…', on_press=app.show_collection_storage, style=Pack(height=48)))
        app.show_legacy_choice = toga.Switch('Show Legacy',
            value=getattr(app, 'show_legacy_session', False),
            on_change=app.change_show_legacy, style=Pack(height=48))
        box.add(switch_row(app, 'Show Legacy', app.show_legacy_choice,
            'Show Legacy- folders in Workspaces, file browsers and library shortcuts, '
            'and credential choices whose names start with Legacy. This choice lasts only until the app closes.'))
        from .trusted_wifi import controls as trusted_wifi_controls
        trusted_wifi_controls(app, box)
        box.add(toga.Button('rclone connections…', on_press=app.show_cloud_connections, style=Pack(height=48)))
        box.add(toga.Button('SMB shares…', on_press=app.show_smb_connection, style=Pack(height=48)))
        return box


    def reset(self):
        app = self.app
        box = self.category('Reset')
        box.add(toga.Button('Erase all app data…', on_press=app.show_app_reset, style=Pack(height=48)))
        box.add(SettingsLabel('Delete private files, local app data, settings and metadata. Review the full scope before confirming.'))
        return box


    def help(self):
        app = self.app
        box = self.category('Help')
        if type(app._impl).__module__.startswith('toga_android.'):
            box.add(toga.Button('Developer settings…', on_press=app.open_android_developer_settings, style=Pack(height=48)))
        from ..documentation_ui import show_documentation
        box.add(toga.Button('Mobile documentation', on_press=lambda widget, **kw: show_documentation(app),
                            style=Pack(height=48)))
        return box


    def about(self):
        app = self.app
        box = self.category('About')
        app.build_version_label = toga.Label(build_information(app.version),
            style=Pack(font_size=12, color='#808080'))
        box.add(app.build_version_label)
        return box


@dataclass(frozen=True)
class Category:
    title: str
    factory: str
    arguments: tuple = ()
    camera_required: bool = False


CATEGORIES = (
    Category('App', 'application'), Category('Appearance', 'appearance'), Category('Features', 'features'),
    Category('Audio playback', 'audio'), Category('Camera', 'camera', camera_required=True), Category('Read aloud', 'speech'),
    Category('Markdown', 'text_size', ('Markdown', 'markdown_font_size')),
    Category('Text', 'text_size', ('Text', 'text_font_size')),
    Category('EPUB', 'text_size', ('EPUB', 'epub_font_size')),
    Category('Books & Comics', 'books'), Category('LM Chat', 'chat'),
    Category('Workspaces', 'workspaces'), Category('Reset', 'reset'),
    Category('Help', 'help'), Category('About', 'about'),
)


def settings_sections(app):
    """Return ordered lazy factories; constructing the registry creates no pages."""
    from features.images.mobile.burst_camera import available
    app.settings_status = SettingsLabel(app.preferences.error, style=Pack(margin_top=12))
    owner = SettingsCategories(app)
    from services.mobile_features import enabled
    requirements = {'Camera': ('images',), 'Markdown': ('text_editor',), 'Text': ('text_editor',),
        'EPUB': ('books',), 'Books & Comics': ('books', 'comics', 'pdf'), 'LM Chat': ('lm',)}
    return {entry.title: lambda entry=entry: getattr(owner, entry.factory)(*entry.arguments)
            for entry in CATEGORIES if (not entry.camera_required or available(app))
            and (entry.title not in requirements or any(enabled(app.preferences, name)
                 for name in requirements[entry.title]))}
