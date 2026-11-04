"""Start the staged payload without access to the source checkout's packages."""

from commonUtils.testing.stages import TestStage, stage

TEST_STAGE = TestStage.REGRESSION
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

REPO = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('startup_mobile_tools', REPO / 'mobile_build/tools.py')
mobile_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mobile_tools)


class PackagedStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.payload = Path(temporary.name) / 'payload'
        mobile_tools.stage(REPO, cls.payload, allow_dirty=True)

    def run_payload(self, code, *, timeout=45):
        prefix = '''
from pathlib import Path
import sys
payload = Path(sys.argv[1]).resolve()
from unittest.mock import patch
fixture_home = Path('home').resolve()
fixture_home.mkdir()
patch.object(Path, 'home', return_value=fixture_home).start()

'''
        with TemporaryDirectory() as directory:
            try:
                result = subprocess.run([sys.executable, '-u', '-c', prefix + code, str(self.payload)],
                    cwd=directory,
                    env=dict(os.environ, PYTHONPATH=str(self.payload), TOGA_BACKEND='toga_dummy'),
                    capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired as error:
                self.fail(f'Packaged validation stalled. Child output: {error.stdout!r}\n{error.stderr!r}')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

    def test_home_starts_from_the_payload_with_existing_and_empty_storage(self):
        code = '''
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
assert issubclass(PrivateController, ProviderUI)
assert not issubclass(PrivateController, LocalCryptUI)
assert not (payload / 'mobile/cloud.py').exists()
assert not (payload / 'mobile/localcrypt_ui.py').exists()
print('PACKAGED_PHASE: imports', flush=True)
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
assert Path(mobile.__file__).resolve().is_relative_to(payload)
print('PACKAGED_PHASE: launch', flush=True)
for saved_document in (False, True):
    if saved_document:
        DocumentStore(root / 'Documents').create('Saved note.md', b'# Existing document')
    LogisticsMobile.storage_root = root
    print('PACKAGED_PHASE: application', flush=True)
    app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
    assert app.native_host.state.destination == 'home'
    assert not app._home_status_row.children
    assert app._home_status_row.parent is None
    assert app.home_actions.children[0].text == 'Open Document'
    print('PACKAGED_PHASE: locations', flush=True)
    app.show_locations()
    assert app.loop.run_until_complete(app.refresh_folder_hub())
    discovery = app.folder_controller().discovery
    assert 'All files' in discovery.cached_choices()
    assert 'All files' in app.folder_picker_choices
    from commonUtils.runtime.resources.local import LocalFiles
    from features.text_editor.resources import LocalTextCopies
    print('PACKAGED_PHASE: markdown', flush=True)
    notes = root / 'provider-notes'
    notes.mkdir(exist_ok=True)
    (notes / 'Note.md').write_text('# Packaged Markdown')
    assert app.loop.run_until_complete(app.open_crypt(copies=LocalTextCopies(LocalFiles(notes)), key='Note.md'))
    reader = app.private_sessions.active
    assert reader.crypt_content.children == [reader.crypt_preview]
    reader.toggle_private_preview()
    assert reader.crypt_content.children == [reader.crypt_formatted.view]
    assert reader.crypt_text.value == '# Packaged Markdown'
    assert app.private_sessions.close(reader.session.id, discard=True)
    print('PACKAGED_PHASE: files', flush=True)
    app.loop.run_until_complete(app.show_files(location=('Local files', '')))
    created_name, renamed_name = 'PackagedFolder-' + str(saved_document), 'RenamedFolder-' + str(saved_document)
    app.file_name.value = created_name
    app.loop.run_until_complete(app.new_file_folder())
    provider = app.file_provider
    assert (provider.root / created_name).is_dir(), (provider.root, app.file_path, app.file_status.value)
    app.browser_file_selected(provider.entry(created_name))
    app.file_name.value = renamed_name
    app.loop.run_until_complete(app.rename_file())
    assert (provider.root / renamed_name).is_dir()
    assert not (provider.root / created_name).exists()
    app.file_location.value = renamed_name
    assert app.loop.run_until_complete(app.browse_files())
    assert app.file_path == renamed_name
    from mobile.workspace_navigation import FileDrawer
    drawer = FileDrawer(app.adaptive, 'home')
    assert app.loop.run_until_complete(drawer.refresh())
    assert any(row['name'] == renamed_name for row in drawer.provider.list(''))
    assert not app.cloud_busy and app._crypt_cancel is None
    print('PACKAGED_PHASE: close', flush=True)
    app.main_window.close()
    app.loop.close()
print('PACKAGED_HOME_OK')
'''
        self.assertIn('PACKAGED_HOME_OK', self.run_payload(code))

    @stage(TestStage.EXTENDED)
    def test_packaged_help_links_restore_root_catalog(self):
        code = '''
import mobile
from mobile.app import LogisticsMobile
LogisticsMobile.storage_root = Path('private').resolve()
app = LogisticsMobile('Packaged help', 'io.github.ispaure.logisticsmobile')
print('PACKAGED_PHASE: documentation', flush=True)
from mobile.documentation_ui import show_documentation
owner = show_documentation(app)
assert owner.path.name == 'user_mobile.md'
assert owner.catalog.root == Path(mobile.__file__).resolve().parent / 'help/docs'
owner.follow_link(owner.web, '../features/lm/user_mobile/user_mobile.md')
assert owner.catalog.root == Path(mobile.__file__).resolve().parent / 'help/docs'
assert owner.path.name == 'user_mobile.md'
assert owner.back()
assert owner.catalog.root == Path(mobile.__file__).resolve().parent / 'help/docs'
assert not (Path(mobile.__file__).parent / 'help/Python/features/emulation').exists()
assert not (Path(mobile.__file__).parent / 'help/Python/commonUtils').exists()
app.main_window.close()
app.loop.close()
print('PACKAGED_HELP_OK', flush=True)

'''
        self.assertIn('PACKAGED_HELP_OK', self.run_payload(code, timeout=90))
