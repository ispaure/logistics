"""Native visual evidence for the always-expanded Hub; synthetic locations only."""
import asyncio
import json
from pathlib import Path
import traceback
import toga
from uuid import uuid4

from logisticsmobile.app import LogisticsMobile
from .fixtures import capture_window


class FolderHubDesignProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('hub-design-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(self.review())

    async def review(self):
        output = Path(self.paths.cache) / 'folder-hub-design'
        output.mkdir(exist_ok=True)
        report = dict(success=False, synthetic=True)
        try:
            self.show_cloud(present=False)
            pending = getattr(self, 'cloud_restore_task', None)
            if pending:
                await pending
            names = ['Server-LLib-' + name for name in ('3D', 'Calibre', 'ComicRack', 'Media', 'ROM', 'Youtube')]
            names += ['Server-Perforce', 'Server-Perforce-2', 'Server-Perforce-3', 'System-Backups']
            loaded = {names[index] for index in (0, 2, 3, 6, 7)}
            choices = {}
            for name in names + ['Home Mac']:
                copy = dict(name=name, source='Remote', kind='remote', value=(name, ''), remote=name)
                choices[name] = dict(copy, copies=[copy])
            local = dict(name='Notes', source='Local', kind='local', value='Notes', remote=None)
            choices['Notes'] = dict(local, copies=[local])
            owner = self.folder_controller()
            owner.folder_choices = lambda: choices
            owner.network_share_remotes = lambda: {'Home Mac'}
            owner.loaded_remote_names = lambda: sorted(loaded)
            self.cloud_crypt_remotes = set(names)
            self.remember_credential_association('Fixture.zip', names, session_only=True)
            self.show_locations()
            self.change_folder_source('rclone')
            assert [button.text for button in self.folder_source_buttons.values()] == ['Local', 'Cloud', 'Home Server']
            for name in names:
                button = self.folder_buttons[name]
                icon = button.parent.children[0]
                expected = 'folder_unlocked' if name in loaded else 'folder_locked'
                assert icon.control_icon == expected, (name, icon.control_icon)
                assert icon._impl._surface_roles[1] == expected
                assert ('unlocked' if name in loaded else 'locked') in button.accessible_name
                assert button.style.font_weight == 'bold'
            assert all(not hasattr(label, 'on_press') for label in self.folder_tree_buttons.values())
            for label in self.folder_tree_buttons.values():
                assert label.style.font_weight == 'normal'
                assert label.parent.children[0].control_icon == 'group'
            self.folder_collapsed.add(('Server',))
            self.update_folder_list(choices)
            assert set(self.folder_buttons) == set(names)
            backend = type(self._impl).__module__
            for dark in (False, True):
                if backend.startswith('toga_iOS.'):
                    self.main_window._impl.native.overrideUserInterfaceStyle = 2 if dark else 1
                else:
                    # Toga's activity is not an AppCompatActivity. Apply the
                    # application mode through Android's actual uiMode service.
                    self._impl.native.getSystemService('uimode').setApplicationNightMode(2 if dark else 1)
                await asyncio.sleep(1)
                self.refresh_native_theme()
                await asyncio.sleep(.4)
                if backend.startswith('toga_android.'):
                    assert (self._impl.native.getResources().getConfiguration().uiMode & 0x30 == 0x20) == dark
                def left(widget):
                    native = widget._impl.native
                    if backend.startswith('toga_iOS.'):
                        return float(native.convertRect(native.bounds, toView=self.main_window._impl.native).origin.x)
                    from java import jarray, jint
                    point = jarray(jint)(2)
                    native.getLocationOnScreen(point)
                    return float(point[0]) / float(native.getResources().getDisplayMetrics().density)
                server = left(self.folder_tree_buttons[('Server',)])
                library = left(self.folder_tree_buttons[('Server', 'LLib')])
                book = self.folder_buttons['Server-LLib-3D']
                book_label = left(book)
                book_icon = left(book.parent.children[0])
                depot = self.folder_buttons['Server-Perforce']
                child_icon = left(self.folder_buttons['Server-Perforce-2'].parent.children[0])
                assert library >= server + 24, ('Library must indent from Server', server, library)
                assert book_label >= library + 24, ('Folder label must indent from Library', library, book_label)
                assert book_icon > library, ('Child folder icon must follow parent label', library, book_icon)
                assert child_icon > left(depot), ('Nested folder icon must follow parent folder label', left(depot), child_icon)
                report['indent_positions'] = dict(server=server, library=library, folder=book_label, folder_icon=book_icon)
                await capture_window(self, output / ('cloud-dark.png' if dark else 'cloud-light.png'))
            for source, filename in [('Network shares', 'home-server.png'), ('Local', 'local.png')]:
                self.change_folder_source(source)
                await asyncio.sleep(.4)
                await capture_window(self, output / filename)
            self.change_folder_source('rclone')
            if backend.startswith('toga_android.'):
                from logisticsmobile.appearance import configure_android_eink
                self.preferences.values['android_eink'] = 'true'
                configure_android_eink(self)
                self.refresh_native_theme()
                await asyncio.sleep(.5)
                await capture_window(self, output / 'cloud-monochrome.png')
            from types import SimpleNamespace
            self.show_cloud()
            provider = SimpleNamespace(root=Path('/remote/Fixture'), remote='Fixture', relative=lambda path: path)
            self.remote_browser.set_entries(provider, '', [
                dict(name='Comics', path='Comics', directory=True, size=0, modified=''),
                dict(name='note.md', path='note.md', directory=False, size=12, modified=''),
            ])
            self.cloud_status.value = 'ComicRack'
            self.remote_browser.location_bar.update('', remote=True, encrypted=True, unlocked=True)
            indicators = self.remote_browser.location_bar.storage_icons.children
            assert [item.control_icon for item in indicators] == ['storage_remote', 'folder_unlocked']
            assert indicators[-1]._impl._surface_roles[1] == 'folder_unlocked'
            assert isinstance(self.cloud_status, toga.Label)
            assert not hasattr(self.remote_browser, 'options_button')
            assert self.remote_browser.location_bar.children[-1] is self.remote_browser.search_button
            report['browser_header_search_only'] = True
            assert self.remote_browser.search_panel not in self.remote_browser.widget.children
            await asyncio.sleep(.4)
            await capture_window(self, output / 'browser-unlocked.png')
            self.remote_browser.search_button.on_press()
            assert self.remote_browser.search_panel in self.remote_browser.widget.children
            await asyncio.sleep(.4)
            await capture_window(self, output / 'browser-search.png')
            self.remote_browser.close_search_button.on_press()
            assert self.remote_browser.search_panel not in self.remote_browser.widget.children
            report.update(success=True, backend=backend, folders=len(names),
                          independent_locks=True, permanent_nesting=True,
                          source_labels=['Local', 'Cloud', 'Home Server'])
        except Exception:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print('FOLDER_HUB_DESIGN=' + json.dumps(report), flush=True)


def main():
    return FolderHubDesignProbe('Folder Hub Preview', 'io.github.ispaure.logisticsfolderhubcapture')
