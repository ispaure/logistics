"""Compact preference rows and offline installed-build information."""
import asyncio
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
from .forms import SettingsLabel, switch_row, page_button
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
            'Resume the last active document when the app starts.'))
        box.add(switch_row(app, 'Close saved documents on restart', app.clear_documents_choice,
            'Close documents with no unsaved changes when the app restarts. Files and drafts are kept. '
            'The last active document stays open if Restore last document is on.'))
        box.add(toga.Label('Preferences save automatically on this device.', style=Pack(font_size=12)))
        box.add(toga.Button('Reload preferences', on_press=app.reload_preferences, style=Pack(height=48)))
        box.add(SettingsLabel('Reread the preferences file after editing or repairing it outside the app. '
                              'Changes made in Settings are already saved.'))
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
        from .accent import AccentControls
        app.accent_controls = AccentControls(app)
        box.add(app.accent_controls)
        app.snow_choice = toga.Switch('Seasonal snow',
            value=app.preferences.values['seasonal_snow'] == 'true', style=Pack(height=48))
        box.add(switch_row(app, 'Seasonal snow', app.snow_choice,
            'Show falling snow from December 15 to January 2. Hidden in high-contrast / E Ink mode.'))
        app.snow_choice.on_change = app.change_seasonal_snow
        if not type(app._impl).__module__.startswith('toga_android.'):
            return box
        app.android_eink_choice = toga.Switch('High contrast / E Ink',
            value=app.preferences.values['android_eink'] == 'true', style=Pack(height=48))
        box.add(switch_row(app, 'High contrast / E Ink', app.android_eink_choice,
            'Use black text on white, stronger borders and simpler controls. Overrides dark mode and reader colors; images stay unchanged.'))
        app.android_eink_choice.on_change = app.change_android_eink
        return box

    def features(self):
        from ..feature_settings import feature_controls
        box = self.category('Features')
        feature_controls(self.app, box)
        preview = toga.Switch('Notebooks: Paper Pro colors',
            value=self.app.preferences.values['notebook_paper_preview'] == 'true',
            style=Pack(height=48))
        preview.on_change = lambda widget, **kw: self.app.preferences.save(
            notebook_paper_preview='true' if widget.value else 'false')
        box.add(switch_row(self.app, 'Notebook preview', preview,
            'Approximate the muted colors of Paper Pro / Paper Pro Move. Reopen notebooks to apply. Saved ink is unchanged.'))
        return box


    def speech(self):
        app = self.app
        box = self.category('Read aloud')
        box.add(speech_voice_setting(app))
        return box

    def privacy(self):
        app = self.app
        box = self.category('Privacy & Security')
        from .trusted_wifi import controls as trusted_wifi_controls
        trusted_wifi_controls(app, box)
        app.session_speech_choice = toga.Switch('Session-only speech while locked',
            value=app.preferences.values['session_speech_when_locked'] == 'true',
            on_change=app.change_session_speech, style=Pack(height=48))
        box.add(switch_row(app, 'Session-only speech while locked', app.session_speech_choice,
            'Keep read-aloud playing when the screen locks, including system playback controls. '
            'Applies to session-only documents already being read; new files stay locked.'))
        box.add(SettingsLabel('Protected audio outputs', style=Pack(font_weight='bold')))
        from .audio import controls as audio_controls
        audio_controls(app, box)
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
        box.add(toga.Label('Pinch while reading to change this size.', style=Pack(font_size=12)))
        if title in {'Markdown', 'EPUB'}:
            justify_key = title.lower() + '_justify'
            justify = toga.Switch('Justify text', value=app.preferences.values[justify_key] == 'true', style=Pack(height=48))
            setattr(app, justify_key + '_choice', justify)
            box.add(switch_row(app, 'Justify text', justify,
                'Align text to both the left and right edges.'))
            justify.on_change = app.save_preferences
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
        box.add(toga.Label('While holding the magnifier, tap − or + to change its zoom. Applies to comics and PDFs.', style=Pack(font_size=12)))
        box.add(page_button('Saved books & comics…', on_press=app.show_saved_files, style=Pack(height=48)))
        box.add(toga.Label('For page layout and colors, open Appearance in the reader.', style=Pack(font_size=12)))
        return box


    def chat(self):
        app = self.app
        box = self.category('LM Chat')
        box.add(page_button('Server & generation settings…', on_press=lambda widget, **kw:
            app.show_chat_configuration(destination='settings'), style=Pack(height=48)))
        return box


    def workspaces(self):
        app = self.app
        box = self.category('Workspaces')
        if type(app._impl).__module__.startswith('toga_android.'):
            box.add(page_button('File storage…', on_press=app.show_collection_storage, style=Pack(height=48)))
        app.show_legacy_choice = toga.Switch('Show Legacy',
            value=getattr(app, 'show_legacy_session', False),
            on_change=app.change_show_legacy, style=Pack(height=48))
        box.add(switch_row(app, 'Show Legacy', app.show_legacy_choice,
            'Show older folders and credentials named Legacy. Resets when the app closes.'))
        from .reader_history import migration_controls
        migration_controls(app, box)
        box.add(page_button('rclone connections…', on_press=app.show_cloud_connections, style=Pack(height=48)))
        box.add(page_button('SMB shares…', on_press=app.show_smb_connection, style=Pack(height=48)))
        return box


    def reset(self):
        app = self.app
        box = self.category('Reset')
        from .reader_history import controls as history_controls
        history_controls(app, box)
        box.add(page_button('Erase all app data…', on_press=app.show_app_reset, style=Pack(height=48)))
        box.add(SettingsLabel('Delete private files, local app data, settings and metadata. Review the full scope before confirming.'))
        return box


    def help(self):
        app = self.app
        box = self.category('Help')
        from ..documentation_ui import show_documentation
        box.add(page_button('Mobile documentation', on_press=lambda widget, **kw: show_documentation(app),
                            style=Pack(height=48)))
        box.add(page_button('About', on_press=self.show_about, style=Pack(height=48)))
        if type(app._impl).__module__.startswith('toga_android.'):
            from .forms import connection_disclosure, settings_presentation, fit_section
            developer = toga.Button('Android Developer Settings…',
                on_press=app.open_android_developer_settings, style=Pack(height=48))
            more, _ = connection_disclosure('More', [developer],
                on_toggle=lambda panel: fit_section(panel, app.settings_navigation.detail_width - 32))
            settings_presentation(developer.parent)
            more._settings_managed_content = True
            box.add(more)
        return box

    def show_about(self, widget=None, **kwargs):
        app = self.app
        if not app.checkpoint():
            return
        navigation = app.settings_navigation
        navigation.fit_detail('About')
        view = navigation.options['About']
        navigation.detach(view)
        app.show_view(view, checkpoint=False, destination='settings', route='settings-about', title='About')

    def about(self):
        app = self.app
        box = self.category('About')
        label = app.build_version_label = SettingsLabel(
            (app.version or 'Development build') + '\nLoading build information…',
            style=Pack(font_size=12, color='#808080'))
        box.add(label)

        async def load_information():
            try:
                text = await asyncio.to_thread(build_information, app.version)
            except Exception:
                # Keep About usable even if an old/malformed payload cannot be read.
                text = (app.version or 'Development build') + '\nBuild information unavailable.'
            label.text = text

        app.build_information_task = app.loop.create_task(load_information())
        from .licenses import show_licenses
        box.add(page_button('Open-source licenses', on_press=lambda widget, **kw: show_licenses(app),
                            style=Pack(height=48)))
        return box


@dataclass(frozen=True)
class Category:
    title: str
    factory: str
    arguments: tuple = ()
    camera_required: bool = False


CATEGORIES = (
    Category('App', 'application'), Category('Appearance', 'appearance'), Category('Features', 'features'),
    Category('Camera', 'camera', camera_required=True), Category('Read aloud', 'speech'),
    Category('Markdown', 'text_size', ('Markdown', 'markdown_font_size')),
    Category('Text', 'text_size', ('Text', 'text_font_size')),
    Category('EPUB', 'text_size', ('EPUB', 'epub_font_size')),
    Category('Books & Comics', 'books'), Category('LM Chat', 'chat'),
    Category('Workspaces', 'workspaces'), Category('Privacy & Security', 'privacy'), Category('Reset', 'reset'),
    Category('Help', 'help'), Category('About', 'about'),
)


def settings_sections(app):
    """Return ordered lazy factories; constructing the registry creates no pages."""
    from features.images.mobile.burst_camera import available
    app.settings_status = SettingsLabel(app.preferences.error, style=Pack(margin_top=12))
    owner = SettingsCategories(app)
    from services.mobile_features import enabled
    requirements = {'Camera': ('images',), 'Markdown': ('text_editor', 'notes_library'), 'Text': ('text_editor', 'notes_library'),
        'EPUB': ('books',), 'Books & Comics': ('books', 'comics', 'pdf'), 'LM Chat': ('lm',)}
    return {entry.title: lambda entry=entry: getattr(owner, entry.factory)(*entry.arguments)
            for entry in CATEGORIES if (not entry.camera_required or available(app))
            and (entry.title not in requirements or any(enabled(app.preferences, name)
                 for name in requirements[entry.title]))}
