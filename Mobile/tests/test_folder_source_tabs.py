"""Source isolation, credential defaults and iOS shared-root browsing."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from logisticsmobile.app import LogisticsMobile
from features.rclone.mobile.storage_location import use_shared_local, _shared_local_roots


class FolderSourceTabTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name) / 'private'
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_cloud(present=False)

    def tearDown(self):
        _shared_local_roots.pop(self.app.private_root, None)
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_tabs_isolate_sources_and_reset_rclone_credential(self):
        app = self.app
        app.cloud_remote.items = ['Personal drive', 'Work drive', 'Home Mac']
        app.remember_credential_association('Personal.zip', ['Personal drive'], session_only=True)
        app.remember_credential_association('Work.zip', ['Work drive'], session_only=True)
        app.remember_credential_association('Session network shares', ['Home Mac'], session_only=True)
        (app.private_root / 'LocalFiles' / 'Notes').mkdir(parents=True)
        app.show_locations()
        self.assertEqual(app.folder_source, 'rclone')
        self.assertEqual(set(app.folder_buttons), {'Personal drive', 'Work drive'})
        self.assertEqual(set(app.folder_credentials), {'All', 'Personal', 'Work'})
        app.folder_credential.value = 'Personal'
        self.assertEqual(set(app.folder_buttons), {'Personal drive'})
        app.folder_source_buttons['Local'].on_press()
        self.assertEqual(set(app.folder_buttons), {'All files', 'Notes'})
        self.assertFalse(app.folder_picker_header.children)
        app.folder_source_buttons['Network shares'].on_press()
        self.assertEqual(set(app.folder_buttons), {'Home Mac'})
        self.assertFalse(app.folder_picker_header.children)
        app.show_locations()
        self.assertEqual(app.folder_source, 'Network shares')
        app.folder_source_buttons['rclone'].on_press()
        self.assertEqual(app.folder_credential.value, 'All')
        self.assertEqual(set(app.folder_buttons), {'Personal drive', 'Work drive'})
        self.assertIs(app.folder_picker_header.children[0], app.folder_credential_row)

    def test_ios_local_tab_opens_files_beside_local_and_other_subfolders(self):
        app = self.app
        documents = Path(self.directory.name) / 'Documents'
        (documents / 'Local' / 'Managed').mkdir(parents=True)
        (documents / 'Notes').mkdir()
        (documents / 'note.md').write_text('# Shared root')
        (documents / 'Notes' / 'nested.txt').write_text('Nested file')
        use_shared_local(app.private_root, documents)
        app.show_locations()
        app.change_folder_source('Local')
        self.assertEqual(set(app.folder_buttons), {'All files', 'Notes'})
        app.loop.run_until_complete(app.folder_buttons['All files'].on_press())
        self.assertEqual(app.file_provider.root, documents)
        self.assertEqual({row['name'] for row in app.file_rows.values()}, {'Notes', 'note.md'})
        with self.assertRaises(ValueError):
            app.file_provider.entry('Local/Managed')
        app.show_locations()
        app.loop.run_until_complete(app.folder_buttons['Notes'].on_press())
        self.assertEqual(app.file_path, 'Notes')
        self.assertEqual({row['name'] for row in app.file_rows.values()}, {'nested.txt'})

    def test_mapped_copies_remain_with_their_remote_owner(self):
        from logisticsmobile.folder_hub import source_choices
        choices = {'Offline': dict(source='Local', kind='job', remote='Drive', copies=[
            dict(source='Local', remote='Drive'), dict(source='Remote', remote='Drive')]),
            'Share copy': dict(source='Local', kind='job', remote='Mac', copies=[])}
        self.assertEqual(set(source_choices(choices, 'rclone', {'Mac'})), {'Offline'})
        self.assertEqual(set(source_choices(choices, 'Network shares', {'Mac'})), {'Share copy'})
        self.assertEqual(source_choices(choices, 'Local', {'Mac'}), {})

    def test_rows_show_icons_for_each_available_storage_copy(self):
        from test_mirror_jobs import MirrorClient
        class Client(MirrorClient):
            def cancel(self): pass
        app = self.app
        app.cloud_client = Client()
        app.cloud_remote.items = ['Remote', 'Secret', 'Online']
        store = app.mirror_store()
        local, _ = store.create(app.cloud_client, 'Remote', 'folder', storage='Local')
        crypt, _ = store.create(app.cloud_client, 'Secret', 'folder', storage='LocalCrypt')
        (app.private_root / 'LocalFiles' / 'Notes').mkdir(parents=True)
        app.show_locations()

        def icons(name):
            return [child.control_icon for child in app.folder_buttons[name].parent.children
                    if getattr(child, 'control_icon', '').startswith('storage_')]

        self.assertEqual(icons('Online'), ['storage_remote'])
        self.assertEqual(icons(local['target']), ['storage_local', 'storage_remote'])
        self.assertEqual(icons(crypt['target']), ['storage_crypt', 'storage_remote'])
        app.change_folder_source('Local')
        self.assertEqual(icons('Notes'), ['storage_local'])
        self.assertEqual(icons('All files'), ['storage_local'])
        app.change_folder_source('rclone')
        store.target(crypt).rename(store.target(crypt).with_name('unmapped'))
        app.show_locations()
        self.assertEqual(icons('Secret'), ['storage_remote'])
