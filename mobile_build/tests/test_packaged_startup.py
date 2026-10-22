"""Start the staged payload without access to the source checkout's packages."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('startup_mobile_tools', REPO / 'mobile_build/tools.py')
mobile_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mobile_tools)


class PackagedStartupTests(unittest.TestCase):
    def test_home_starts_from_the_payload_with_existing_and_empty_storage(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / 'payload'
            mobile_tools.stage(REPO, payload, allow_dirty=True)
            code = '''
from pathlib import Path
import mobile
import sys
from mobile.folder_discovery import FolderDiscovery
from mobile.file_operations import FileOperations
from mobile.folder_listing import FolderListing
assert not any(name.startswith(('PySide', 'toga')) for name in sys.modules)
from features.rclone.transfers.transfer_options import TransferOptions
assert TransferOptions().copy_links
from features.rclone.mobile.cloud import CloudClient
from features.rclone.mobile.cloud_ui import CloudUI
from mobile.provider_ui import ProviderUI
from mobile.private_sessions import PrivateController
from features.rclone.localcrypt.mobile.ui import LocalCryptUI
from services.documents.archive_access import NativeArchiveAccess
assert CloudClient.__module__ == 'features.rclone.mobile.cloud'
assert CloudUI.__module__ == 'features.rclone.mobile.cloud_ui'
assert ProviderUI.__module__ == 'mobile.provider_ui'
assert NativeArchiveAccess.__module__ == 'services.documents.archive_access'
assert issubclass(PrivateController, ProviderUI)
assert not issubclass(PrivateController, LocalCryptUI)
assert not Path('payload/mobile/cloud.py').exists()
assert not Path('payload/mobile/localcrypt_ui.py').exists()
from mobile.app import LogisticsMobile
from mobile.documents import DocumentStore
# Briefcase still starts the installed logisticsmobile entry point. Exercise
# that generated launcher against the packaged application, without a UI loop.
import runpy
from unittest.mock import Mock, patch
launcher_app = Mock()
with patch('mobile.app.main', return_value=launcher_app) as start:
    runpy.run_module('logisticsmobile', run_name='__main__')
start.assert_called_once_with()
launcher_app.main_loop.assert_called_once_with()
root = Path('private').resolve()
root.mkdir(exist_ok=True)
assert Path(mobile.__file__).resolve().is_relative_to(Path('payload').resolve())
for saved_document in (False, True):
    if saved_document:
        DocumentStore(root / 'Documents').create('Saved note.md', b'# Existing document')
    LogisticsMobile.storage_root = root
    app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
    assert app.native_host.state.destination == 'home'
    assert app.body.children[0].content.children[0].text == 'Your workspace'
    from mobile.documentation_ui import show_documentation
    owner = show_documentation(app)
    assert owner.path.name == 'user_mobile.md'
    assert owner.catalog.root == Path(mobile.__file__).resolve().parent / 'help/docs'
    owner.follow_link(owner.web, '../../Python/features/lm/docs/user_mobile/user_mobile.md')
    assert owner.catalog.root == Path(mobile.__file__).resolve().parent / 'help/Python/features/lm/docs'
    assert owner.path.name == 'user_mobile.md'
    assert owner.back()
    assert owner.catalog.root == Path(mobile.__file__).resolve().parent / 'help/docs'
    assert not (Path(mobile.__file__).parent / 'help/Python/features/emulation').exists()
    assert not (Path(mobile.__file__).parent / 'help/Python/commonUtils').exists()
    app.show_locations()
    assert app.loop.run_until_complete(app.refresh_folder_hub())
    discovery = app.folder_controller().discovery
    assert type(discovery).__module__ == 'mobile.folder_discovery'
    assert 'All files' in discovery.cached_choices()
    assert 'All files' in app.folder_picker_choices
    from commonUtils.runtime.resources.local import LocalFiles
    from features.text_editor.resources import LocalTextCopies
    notes = root / 'provider-notes'
    notes.mkdir(exist_ok=True)
    (notes / 'Note.md').write_text('# Packaged Markdown')
    assert app.loop.run_until_complete(app.open_crypt(copies=LocalTextCopies(LocalFiles(notes)), key='Note.md'))
    reader = app.private_sessions.active
    assert type(reader._provider_markdown).__module__ == 'features.text_editor.mobile.provider_markdown'
    assert reader.crypt_content.children == [reader.crypt_preview]
    reader.toggle_private_preview()
    assert reader.crypt_content.children == [reader.crypt_formatted.view]
    assert reader.crypt_text.value == '# Packaged Markdown'
    assert app.private_sessions.close(reader.session.id, discard=True)
    app.loop.run_until_complete(app.show_files())
    created_name, renamed_name = 'PackagedFolder-' + str(saved_document), 'RenamedFolder-' + str(saved_document)
    app.file_name.value = created_name
    app.loop.run_until_complete(app.new_file_folder())
    provider = app.file_provider
    assert (provider.root / created_name).is_dir()
    assert type(app.file_operations()).__module__ == 'mobile.file_operations'
    app.browser_file_selected(provider.entry(created_name))
    app.file_name.value = renamed_name
    app.loop.run_until_complete(app.rename_file())
    assert (provider.root / renamed_name).is_dir()
    assert not (provider.root / created_name).exists()
    assert type(app.folder_listing()).__module__ == 'mobile.folder_listing'
    app.file_location.value = renamed_name
    assert app.loop.run_until_complete(app.browse_files())
    assert app.file_path == renamed_name
    from mobile.workspace_navigation import FileDrawer
    drawer = FileDrawer(app.adaptive, 'home')
    assert app.loop.run_until_complete(drawer.refresh())
    assert type(drawer.listing).__module__ == 'mobile.folder_listing'
    assert any(row['name'] == renamed_name for row in drawer.provider.list(''))
    assert not app.cloud_busy and app._crypt_cancel is None
    app.main_window.close()
    app.loop.close()
print('PACKAGED_HOME_OK')
'''
            result = subprocess.run([sys.executable, '-c', code], cwd=root,
                env=dict(os.environ, PYTHONPATH=str(payload), TOGA_BACKEND='toga_dummy'),
                capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PACKAGED_HOME_OK', result.stdout)
