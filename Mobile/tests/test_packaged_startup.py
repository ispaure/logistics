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
    assert app.body.children[0].content.children[0].text == 'Welcome to Logistics'
    app.main_window.close()
    app.loop.close()
print('PACKAGED_HOME_OK')
'''
            result = subprocess.run([sys.executable, '-c', code], cwd=root,
                env=dict(os.environ, PYTHONPATH=str(payload), TOGA_BACKEND='toga_dummy'),
                capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PACKAGED_HOME_OK', result.stdout)
