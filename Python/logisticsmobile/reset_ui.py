"""Explicit destructive reset scope, separate from changing a collection drive."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from .settings_ui import SettingsLabel, fit_section
from .app_reset import schedule_reset, reset_android


def is_ios(app):
    return type(app._impl).__module__.startswith('toga_iOS.')


class ResetUI:
    def show_app_reset(self, widget=None, **kwargs):
        app = self.app
        ios = is_ios(app)
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        self.reset_page = box
        box.add(SettingsLabel('Erase all app data', style=Pack(font_size=22)))
        box.add(SettingsLabel('Deletes private documents and unsaved drafts, imported books, chat, saved credentials and device keys, settings, transfer mappings, reading progress, metadata and caches.'))
        box.add(SettingsLabel('Also deletes every file in On My iPhone / iPad → Logistics, including Local and files you added in Files.' if ios
            else 'Also deletes internal Local and LocalCrypt files. Android closes the app and resets its permissions.'))
        box.add(SettingsLabel('SD-card and shared-storage Logistics folders, cloud files and SMB server files are kept. You will need the original credential ZIPs and passwords to unlock retained LocalCrypt files.'))
        box.add(SettingsLabel('On iOS, erasure runs before startup after you fully close Logistics in the app switcher and reopen it. Until then the app is locked on a reset notice.' if ios
            else 'Android erases this app’s data immediately. Reopen Logistics to start fresh.'))
        box.add(SettingsLabel('This cannot be undone. Export anything you need first. Type ERASE to continue.'))
        self.reset_phrase = toga.TextInput(placeholder='ERASE', on_change=self.reset_phrase_changed, style=Pack(height=48))
        self.reset_button = toga.Button('Erase on next launch…' if ios else 'Erase all app data…',
            enabled=False, on_press=self.confirm_app_reset, style=Pack(height=48))
        self.reset_status = SettingsLabel('')
        box.add(self.reset_phrase, self.reset_button, self.reset_status)
        fit_section(box, max(280, app.adaptive.content_width('settings')))
        app.show_view(toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1)),
                      destination='settings', route='app-reset', title='Erase app data')

    def reset_phrase_changed(self, widget=None, **kwargs):
        if hasattr(self, 'reset_button'):
            self.reset_button.enabled = self.reset_phrase.value == 'ERASE'

    async def confirm_app_reset(self, widget=None, **kwargs):
        app = self.app
        if getattr(self, '_reset_confirming', False) or self.reset_phrase.value != 'ERASE':
            return
        self._reset_confirming = True
        self.reset_button.enabled = False
        try:
            if not self.reset_available():
                return
            ios = is_ios(app)
            if not await app.main_window.dialog(toga.ConfirmDialog('Permanently erase all app data?',
                'All private app files, drafts, settings, metadata, chat and saved credentials will be lost. '
                + ('All files in the Logistics folder in Files will also be lost. Erasure starts when you fully close and reopen the app. ' if ios else 'Internal Local and LocalCrypt files will also be lost. Android will close the app. ')
                + 'SD/shared collections and remote server files are kept. This cannot be undone.')):
                return
            if not self.reset_available():
                return
            if ios:
                schedule_reset(app.private_root)
                app._reset_scheduled = True
                app.scene_manager.app._reset_scheduled = True
                app.active_host = False
                from .markdown_speech import stop_markdown_speech
                from features.books.mobile.media_controls import stop_media
                stop_markdown_speech(app)
                stop_media(app)
                for name in ('cloud_client', 'chat_client'):
                    client = getattr(app, name, None)
                    if client is not None:
                        client.cancel()
                notice = toga.Box(style=Pack(direction=COLUMN, margin=24))
                notice.add(SettingsLabel('Reset is ready', style=Pack(font_size=22)))
                notice.add(SettingsLabel('Fully close Logistics in the app switcher, then reopen it. The listed app data will be erased before any documents or services load.'))
                notice.add(SettingsLabel('The app stays locked until you restart it.'))
                fit_section(notice, max(280, app.adaptive.content_width('settings')))
                app.main_window.content = notice
            else:
                reset_android(app)
                self.reset_status.text = 'Android is erasing app data. Reopen Logistics when it closes.'
        except (OSError, ValueError) as error:
            self.reset_status.text = 'Reset could not start: ' + str(error)
        finally:
            self._reset_confirming = False
            self.reset_button.enabled = self.reset_phrase.value == 'ERASE'

    def reset_available(self):
        app = self.app
        if (getattr(app, 'cloud_busy', False) or getattr(app, 'transfer_busy', False)
                or getattr(app, 'chat_busy', False) or getattr(self, '_storage_changing', False)):
            self.reset_status.text = 'Wait for transfers and other operations to finish, then retry.'
            return False
        if len(app.scene_manager.owners.hosts) > 1:
            self.reset_status.text = 'Close the other Logistics windows before resetting app data.'
            return False
        return True
