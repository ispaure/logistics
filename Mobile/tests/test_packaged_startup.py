"""Start the staged payload without access to the source checkout's packages."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('startup_mobile_tools', REPO / 'Mobile/tools.py')
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
import logisticsmobile
from features.rclone.transfers.transfer_options import TransferOptions
assert TransferOptions().copy_links
from features.rclone.mobile.cloud import CloudClient
from features.rclone.mobile.cloud_ui import CloudUI
from logisticsmobile.provider_ui import ProviderUI
from logisticsmobile.private_sessions import PrivateController
from features.rclone.localcrypt.mobile.ui import LocalCryptUI
from services.archive_access import NativeArchiveAccess
assert CloudClient.__module__ == 'features.rclone.mobile.cloud'
assert CloudUI.__module__ == 'features.rclone.mobile.cloud_ui'
assert ProviderUI.__module__ == 'logisticsmobile.provider_ui'
assert NativeArchiveAccess.__module__ == 'services.archive_access'
assert issubclass(PrivateController, ProviderUI)
assert not issubclass(PrivateController, LocalCryptUI)
assert not Path('payload/logisticsmobile/cloud.py').exists()
assert not Path('payload/logisticsmobile/localcrypt_ui.py').exists()
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.documents import DocumentStore
root = Path('private').resolve()
root.mkdir(exist_ok=True)
assert Path(logisticsmobile.__file__).resolve().is_relative_to(Path('payload').resolve())
for saved_document in (False, True):
    if saved_document:
        DocumentStore(root / 'Documents').create('Saved note.md', b'# Existing document')
    LogisticsMobile.storage_root = root
    app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
    assert app.native_host.state.destination == 'home'
    assert app.body.children[0].content.children[0].text == 'Your workspace'
    from logisticsmobile.documentation_ui import show_documentation
    owner = show_documentation(app)
    assert owner.path.name == 'user_mobile.md'
    assert owner.catalog.root == Path(logisticsmobile.__file__).resolve().parent / 'help/docs'
    owner.follow_link(owner.web, '../../Python/features/lm/docs/user_mobile/user_mobile.md')
    assert owner.catalog.root == Path(logisticsmobile.__file__).resolve().parent / 'help/Python/features/lm/docs'
    assert owner.path.name == 'user_mobile.md'
    assert owner.back()
    assert owner.catalog.root == Path(logisticsmobile.__file__).resolve().parent / 'help/docs'
    assert not (Path(logisticsmobile.__file__).parent / 'help/Python/features/emulation').exists()
    assert not (Path(logisticsmobile.__file__).parent / 'help/Python/commonUtils').exists()
    app.main_window.close()
    app.loop.close()
print('PACKAGED_HOME_OK')
'''
            result = subprocess.run([sys.executable, '-c', code], cwd=root,
                env=dict(os.environ, PYTHONPATH=str(payload), TOGA_BACKEND='toga_dummy'),
                capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PACKAGED_HOME_OK', result.stdout)
